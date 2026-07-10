"""Job 서비스 — Job 상태·목록 조회 (06_API.md §7).

Job 생성/실행은 ProcessingService·background/worker.py가 담당한다.
여기는 조회만 한다(얇은 서비스, 02 §2).
"""

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.job import Job
from app.repositories.job_repo import JobRepository


class JobService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = JobRepository(db)

    def get(self, job_id: int) -> Job:
        job = self.repo.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id}를 찾을 수 없습니다.")
        return job

    def list_by_dataset(
        self, dataset_id: int, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Job], int]:
        return (
            self.repo.list_by_dataset(dataset_id, limit=limit, offset=offset),
            self.repo.count_by_dataset(dataset_id),
        )
