"""Dataset 서비스 — 데이터셋 생성·조회·CSV export.

업로드 시 대상 Dataset이 지정되지 않으면 기본 Dataset(v1)을 자동 생성한다(승인된 결정 4).
CSV export는 커팅과 같은 비동기 Job 패턴을 따른다: 여기서는 Job 레코드 생성까지만
책임지고(빠르게 202 반환), 실제 CSV 생성은 background/worker.py가 수행한다(06_API.md §4.3).
"""

import csv
import io

from sqlalchemy.orm import Session

from app.audio.naming import pattern_fields
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.dataset import Dataset
from app.models.job import Job
from app.models.segment import Segment
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.segment_repo import SegmentRepository
from app.repositories.source_file_repo import SourceFileRepository
from app.schemas.dataset import DatasetCreate
from app.storage.base import StorageBackend

# 출처 컬럼(자기서술, docs/11 §4) + 자동 추출 메타데이터 컬럼(고정)
# + 라벨 컬럼(Project.label_schema에서 동적으로 붙는다, P1).
_PROVENANCE_COLUMNS = ["project_name", "dataset_name", "dataset_version"]
_METADATA_COLUMNS = [
    "id",
    "filename",
    "storage_path",
    "duration_sec",
    "sample_rate",
    "channels",
    "bit_depth",
    "file_size",
    "format",
    "source_start_sec",
    "is_labeled",
    "created_at",
]
# CSV 표현에서만 반올림하는 실수 컬럼 (DB는 원본 정밀도 유지, docs/11 §3)
_ROUND_SEC_DIGITS = 3


def build_metadata_csv(
    segments: list[Segment],
    label_keys: list[str],
    *,
    project_name: str,
    dataset_name: str,
    dataset_version: str,
) -> str:
    """Segment 목록 → Metadata.csv 문자열(F5).

    - 선두 3컬럼(project/dataset/version)으로 파일 자체가 출처를 말한다 —
      파일을 옮겨도, 여러 CSV를 concat해도 구분이 유지된다(docs/11 §4).
    - 실수 컬럼은 소수점 3자리(1ms)로 반올림 — 표현 계층에서만(docs/11 §3).
    - 도메인 분기 없음(P1): label_keys는 호출자가 Project.label_schema에서 넘겨준다.
    """
    fieldnames = [*_PROVENANCE_COLUMNS, *_METADATA_COLUMNS, *label_keys]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for seg in segments:
        row = {
            "project_name": project_name,
            "dataset_name": dataset_name,
            "dataset_version": dataset_version,
            "id": seg.id,
            "filename": seg.filename,
            "storage_path": seg.storage_path,
            "duration_sec": round(seg.duration_sec, _ROUND_SEC_DIGITS),
            "sample_rate": seg.sample_rate,
            "channels": seg.channels,
            "bit_depth": seg.bit_depth,
            "file_size": seg.file_size,
            "format": seg.format,
            "source_start_sec": round(seg.source_start_sec, _ROUND_SEC_DIGITS),
            "is_labeled": seg.is_labeled,
            "created_at": seg.created_at.isoformat() if seg.created_at else "",
            **{key: seg.labels.get(key, "") for key in label_keys},
        }
        writer.writerow(row)
    return buf.getvalue()


class DatasetService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DatasetRepository(db)
        self.project_repo = ProjectRepository(db)
        self.job_repo = JobRepository(db)
        self.segment_repo = SegmentRepository(db)
        self.source_repo = SourceFileRepository(db)

    def create(self, project_id: int, data: DatasetCreate) -> Dataset:
        self._ensure_project(project_id)
        dataset = Dataset(
            project_id=project_id, name=data.name, version=data.version
        )
        self.repo.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def get(self, dataset_id: int) -> Dataset:
        dataset = self.repo.get(dataset_id)
        if dataset is None:
            raise NotFoundError(f"Dataset {dataset_id}를 찾을 수 없습니다.")
        return dataset

    def list_by_project(
        self, project_id: int, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Dataset], int]:
        self._ensure_project(project_id)
        return (
            self.repo.list_by_project(project_id, limit=limit, offset=offset),
            self.repo.count_by_project(project_id),
        )

    def get_or_create_default(self, project_id: int) -> tuple[Dataset, bool]:
        """프로젝트의 기본 Dataset을 반환. 없으면 v1을 만들고 (dataset, True)."""
        existing = self.repo.first_for_project(project_id)
        if existing is not None:
            return existing, False
        dataset = Dataset(project_id=project_id, name="v1 초기수집", version="v1")
        self.repo.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        return dataset, True

    def _ensure_project(self, project_id: int) -> None:
        if self.project_repo.get(project_id) is None:
            raise NotFoundError(f"Project {project_id}를 찾을 수 없습니다.")

    # --- 삭제 (docs/12 B1) ---

    def collect_storage_paths(self, dataset: Dataset) -> list[str]:
        """dataset에 속한 모든 파일의 논리 경로 (세그먼트 + 원본 + export 결과물)."""
        paths = [s.storage_path for s in self.segment_repo.all_for_dataset(dataset.id)]
        paths += [sf.storage_path for sf in self.source_repo.list_by_dataset(dataset.id)]
        paths += [
            j.result_path
            for j in self.job_repo.list_by_dataset(dataset.id, limit=1000)
            if j.type == "export" and j.result_path
        ]
        return paths

    def delete_source_file(self, source_file_id: int, storage: StorageBackend) -> None:
        """원본 1개 삭제. 참조하는 세그먼트가 있으면 409 (먼저 정리 유도)."""
        source = self.source_repo.get(source_file_id)
        if source is None:
            raise NotFoundError(f"SourceFile {source_file_id}를 찾을 수 없습니다.")
        refs = self.segment_repo.list_by_source_file(source_file_id)
        if refs:
            raise ConflictError(
                f"세그먼트 {len(refs)}개가 이 원본을 참조합니다. "
                "세그먼트를 먼저 삭제하거나 replace_existing 재커팅으로 정리하세요."
            )
        storage.delete(source.storage_path)
        self.source_repo.delete(source)
        self.db.commit()

    def delete_dataset(
        self, dataset_id: int, *, confirm: str, storage: StorageBackend
    ) -> None:
        """dataset 전체 삭제 (cascade + 파일). 이름 확인 필수 — 실수 방지."""
        dataset = self.get(dataset_id)
        if confirm != dataset.name:
            raise ValidationError(
                f"확인 이름이 일치하지 않습니다. dataset 이름 '{dataset.name}'을 "
                "confirm 파라미터로 정확히 전달해야 삭제됩니다."
            )
        for path in self.collect_storage_paths(dataset):
            storage.delete(path)
        self.db.delete(dataset)  # segments/source_files/jobs cascade
        self.db.commit()

    # export 경로 패턴이 쓸 수 있는 필드 (docs/11 §2 — worker가 채운다)
    _EXPORT_PATTERN_FIELDS = {
        "project", "dataset", "version", "date", "project_id", "dataset_id",
    }

    def start_export(self, dataset_id: int) -> Job:
        """CSV export Job을 큐에 넣는다. 실제 생성은 worker가 한다."""
        self.get(dataset_id)  # 존재 확인(404)

        # fail-fast: 경로 패턴의 필드가 전부 지원되는지 (docs/11 §2)
        pattern = get_settings().export_path_pattern
        unknown = [
            f for f in pattern_fields(pattern)
            if f not in self._EXPORT_PATTERN_FIELDS
        ]
        if unknown:
            raise ValidationError(
                f"EXPORT_PATH_PATTERN '{pattern}'에 알 수 없는 필드 {unknown}. "
                f"사용 가능: {sorted(self._EXPORT_PATTERN_FIELDS)}"
            )

        if self.job_repo.has_running(dataset_id, "export"):
            raise ConflictError(
                f"Dataset {dataset_id}에 이미 진행 중인 export Job이 있습니다."
            )
        # 재현성: 실행 당시 패턴을 Job에 기록
        job = Job(
            dataset_id=dataset_id, type="export", status="queued",
            params={"export_path_pattern": pattern},
        )
        self.job_repo.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_latest_export_job(self, dataset_id: int) -> Job:
        """가장 최근 완료된 export Job(다운로드 대상). 없으면 404."""
        self.get(dataset_id)  # 존재 확인
        job = self.job_repo.latest_done(dataset_id, "export")
        if job is None:
            raise NotFoundError(f"Dataset {dataset_id}에 완료된 export가 없습니다.")
        return job

    def list_segments(
        self, dataset_id: int, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Segment], int]:
        self.get(dataset_id)
        return (
            self.segment_repo.list_by_dataset(dataset_id, limit=limit, offset=offset),
            self.segment_repo.count_by_dataset(dataset_id),
        )
