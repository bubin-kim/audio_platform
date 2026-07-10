"""Job 저장소."""

from sqlalchemy import func, select

from app.models.job import Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    model = Job

    def list_by_dataset(
        self, dataset_id: int, *, limit: int = 50, offset: int = 0
    ) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.dataset_id == dataset_id)
            .order_by(Job.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def count_by_dataset(self, dataset_id: int) -> int:
        stmt = (
            select(func.count()).select_from(Job).where(Job.dataset_id == dataset_id)
        )
        return self.db.scalar(stmt) or 0

    def latest_done(self, dataset_id: int, job_type: str) -> Job | None:
        """해당 Dataset·종류에서 가장 최근에 완료된(done) Job. 다운로드 대상 찾기용."""
        stmt = (
            select(Job)
            .where(
                Job.dataset_id == dataset_id,
                Job.type == job_type,
                Job.status == "done",
            )
            .order_by(Job.finished_at.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def has_running(self, dataset_id: int, job_type: str) -> bool:
        """해당 Dataset에 진행 중(queued/running)인 같은 종류 Job이 있는지.

        커팅 중복 실행 방지(409)에 쓴다.
        """
        stmt = (
            select(Job.id)
            .where(
                Job.dataset_id == dataset_id,
                Job.type == job_type,
                Job.status.in_(("queued", "running")),
            )
            .limit(1)
        )
        return self.db.scalars(stmt).first() is not None
