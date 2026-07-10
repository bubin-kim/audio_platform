"""Project 저장소."""

from sqlalchemy import select

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    def list_all(self) -> list[Project]:
        """페이지네이션 없이 전량 조회(대시보드 집계용)."""
        return list(self.db.scalars(select(Project)).all())
