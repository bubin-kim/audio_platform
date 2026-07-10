"""SourceFile 저장소."""

from sqlalchemy import select

from app.models.source_file import SourceFile
from app.repositories.base import BaseRepository


class SourceFileRepository(BaseRepository[SourceFile]):
    model = SourceFile

    def list_by_dataset(self, dataset_id: int) -> list[SourceFile]:
        stmt = (
            select(SourceFile)
            .where(SourceFile.dataset_id == dataset_id)
            .order_by(SourceFile.id.asc())
        )
        return list(self.db.scalars(stmt).all())
