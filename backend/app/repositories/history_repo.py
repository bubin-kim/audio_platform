"""UploadHistory 저장소.

ProcessingHistory는 Job이 겸하므로 여기엔 업로드 이력만 둔다(05 §3.6).
"""

from sqlalchemy import select

from app.models.history import UploadHistory
from app.repositories.base import BaseRepository


class UploadHistoryRepository(BaseRepository[UploadHistory]):
    model = UploadHistory

    def recent(
        self, *, limit: int = 10, project_id: int | None = None
    ) -> list[UploadHistory]:
        """대시보드 '최근 업로드' 용, 최신순. project_id가 있으면 해당 프로젝트로 한정."""
        stmt = select(UploadHistory).order_by(
            UploadHistory.created_at.desc(), UploadHistory.id.desc()
        )
        if project_id is not None:
            stmt = stmt.where(UploadHistory.project_id == project_id)
        stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())
