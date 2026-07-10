"""Processing 서비스 — 커팅 Job 시작 오케스트레이션 (02 §4, §5 / P1).

전략은 registry에서 조회만 한다 — `if cutting_mode == ...` 분기문은 없다.
실제 무거운 처리(파일 읽기·커팅·저장)는 background/worker.py 가 별도 세션으로 수행한다.
이 서비스는 요청 스레드에서 **Job 레코드 생성까지**만 책임진다(빠르게 202 반환).
"""

from typing import Any

from sqlalchemy.orm import Session

from app.audio.cutting import available_strategies
from app.audio.naming import pattern_fields
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.job import Job
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.job_repo import JobRepository
from app.repositories.source_file_repo import SourceFileRepository
from app.schemas.job import ProcessRequest
from app.services.label_validation import validate_labels


class ProcessingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.dataset_repo = DatasetRepository(db)
        self.source_repo = SourceFileRepository(db)
        self.job_repo = JobRepository(db)

    def start_cutting(self, dataset_id: int, req: ProcessRequest) -> Job:
        dataset = self.dataset_repo.get(dataset_id)
        if dataset is None:
            raise NotFoundError(f"Dataset {dataset_id}를 찾을 수 없습니다.")
        project = dataset.project

        if project.cutting_mode not in available_strategies():
            raise ValidationError(
                f"알 수 없는 cutting_mode='{project.cutting_mode}'. "
                f"사용 가능: {available_strategies()}"
            )

        validate_labels(project.label_schema, req.common_labels)
        self._validate_naming_resolvable(project.naming_pattern, req.common_labels)

        if self.job_repo.has_running(dataset_id, "cutting"):
            raise ConflictError(
                f"Dataset {dataset_id}에 이미 진행 중인 커팅 Job이 있습니다."
            )

        source_files = self._resolve_source_files(dataset_id, req.source_file_ids)
        if not source_files:
            raise ValidationError("커팅할 SourceFile이 없습니다.")

        cutting_params = {**project.cutting_params, **(req.params_override or {})}

        params: dict[str, Any] = {
            "cutting_mode": project.cutting_mode,
            "cutting_params": cutting_params,
            "naming_pattern": project.naming_pattern,
            "label_schema": project.label_schema,
            "common_labels": req.common_labels,
            "source_file_ids": [s.id for s in source_files],
        }
        job = Job(
            dataset_id=dataset_id,
            type="cutting",
            status="queued",
            total_items=None,  # 확정 전(전략마다 세그먼트 수를 미리 알 수 없음)
            params=params,
        )
        self.job_repo.add(job)
        dataset.status = "processing"
        self.db.commit()
        self.db.refresh(job)
        return job

    def _validate_naming_resolvable(
        self, naming_pattern: str, common_labels: dict[str, Any]
    ) -> None:
        """naming_pattern의 필드가 커팅 시점에 전부 채워질 수 있는지 fail-fast 검사.

        worker가 각 세그먼트 파일명을 만들 때 쓸 수 있는 값은
        common_labels + 자동값(date, seq)뿐이다. 부족하면 Job이 백그라운드에서
        실패하게 되므로, 시작 전에 400으로 명확히 알려준다.
        """
        auto_fields = {"date", "seq"}
        provided = set(common_labels) | auto_fields
        missing = [f for f in pattern_fields(naming_pattern) if f not in provided]
        if missing:
            raise ValidationError(
                f"naming_pattern '{naming_pattern}'에 필요한 값 {missing}이(가) "
                "없습니다. common_labels로 함께 전달하세요. "
                f"(자동 제공: {sorted(auto_fields)})"
            )

    def _resolve_source_files(
        self, dataset_id: int, source_file_ids: list[int] | None
    ) -> list:
        if source_file_ids is None:
            return self.source_repo.list_by_dataset(dataset_id)
        result = []
        for sid in source_file_ids:
            sf = self.source_repo.get(sid)
            if sf is None or sf.dataset_id != dataset_id:
                raise ValidationError(
                    f"SourceFile {sid}는 Dataset {dataset_id}에 속하지 않습니다."
                )
            result.append(sf)
        return result
