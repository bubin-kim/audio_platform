"""Dataset 저장소."""

from sqlalchemy import func, select

from app.models.dataset import Dataset
from app.repositories.base import BaseRepository


class DatasetRepository(BaseRepository[Dataset]):
    model = Dataset

    def list_by_project(
        self, project_id: int, *, limit: int = 50, offset: int = 0
    ) -> list[Dataset]:
        stmt = (
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .order_by(Dataset.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def count_by_project(self, project_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Dataset)
            .where(Dataset.project_id == project_id)
        )
        return self.db.scalar(stmt) or 0

    def first_for_project(self, project_id: int) -> Dataset | None:
        """프로젝트의 기본(가장 오래된) Dataset. 업로드 시 자동선택용."""
        stmt = (
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .order_by(Dataset.id.asc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()
