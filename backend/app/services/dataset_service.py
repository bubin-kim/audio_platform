"""Dataset 서비스 — 데이터셋 생성·조회·CSV export.

업로드 시 대상 Dataset이 지정되지 않으면 기본 Dataset(v1)을 자동 생성한다(승인된 결정 4).
CSV export는 커팅과 같은 비동기 Job 패턴을 따른다: 여기서는 Job 레코드 생성까지만
책임지고(빠르게 202 반환), 실제 CSV 생성은 background/worker.py가 수행한다(06_API.md §4.3).
"""

import csv
import io

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.dataset import Dataset
from app.models.job import Job
from app.models.segment import Segment
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.segment_repo import SegmentRepository
from app.schemas.dataset import DatasetCreate

# 자동 추출 메타데이터 컬럼(고정) + 라벨 컬럼(Project.label_schema에서 동적으로 붙는다, P1).
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


def build_metadata_csv(segments: list[Segment], label_keys: list[str]) -> str:
    """Segment 목록 → Metadata.csv 문자열(F5). 라벨 컬럼은 label_schema 순서로 펼친다.

    도메인 분기 없음(P1): label_keys는 호출자가 Project.label_schema에서 넘겨준다.
    """
    fieldnames = [*_METADATA_COLUMNS, *label_keys]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for seg in segments:
        row = {
            "id": seg.id,
            "filename": seg.filename,
            "storage_path": seg.storage_path,
            "duration_sec": seg.duration_sec,
            "sample_rate": seg.sample_rate,
            "channels": seg.channels,
            "bit_depth": seg.bit_depth,
            "file_size": seg.file_size,
            "format": seg.format,
            "source_start_sec": seg.source_start_sec,
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

    def start_export(self, dataset_id: int) -> Job:
        """CSV export Job을 큐에 넣는다. 실제 생성은 worker가 한다."""
        self.get(dataset_id)  # 존재 확인(404)
        if self.job_repo.has_running(dataset_id, "export"):
            raise ConflictError(
                f"Dataset {dataset_id}에 이미 진행 중인 export Job이 있습니다."
            )
        job = Job(dataset_id=dataset_id, type="export", status="queued", params={})
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
