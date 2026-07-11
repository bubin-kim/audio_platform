"""Segment 저장소."""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select

from app.models.dataset import Dataset
from app.models.project import Project
from app.models.segment import Segment
from app.repositories.base import BaseRepository


class SegmentRepository(BaseRepository[Segment]):
    model = Segment

    def list_by_dataset(
        self, dataset_id: int, *, limit: int = 50, offset: int = 0
    ) -> list[Segment]:
        stmt = (
            select(Segment)
            .where(Segment.dataset_id == dataset_id)
            .order_by(Segment.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def count_by_dataset(self, dataset_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Segment)
            .where(Segment.dataset_id == dataset_id)
        )
        return self.db.scalar(stmt) or 0

    def add_many(self, segments: Iterable[Segment]) -> list[Segment]:
        """커팅 결과 다수를 한 번에 추가(대량 삽입)."""
        objs = list(segments)
        self.db.add_all(objs)
        self.db.flush()
        return objs

    def list_by_source_file(self, source_file_id: int) -> list[Segment]:
        """특정 원본에서 나온 세그먼트 전량 (재처리 스냅샷·삭제용, docs/10)."""
        stmt = (
            select(Segment)
            .where(Segment.source_file_id == source_file_id)
            .order_by(Segment.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def all_for_dataset(self, dataset_id: int) -> list[Segment]:
        """CSV/통계용: 페이지네이션 없이 전량 조회."""
        stmt = (
            select(Segment)
            .where(Segment.dataset_id == dataset_id)
            .order_by(Segment.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def stats_rows(self, project_id: int | None = None) -> list[dict[str, Any]]:
        """대시보드 집계용 평면 행(Segment + 소속 Project 조인).

        stats_service가 pandas로 계산할 수 있도록 여기서는 조인·필터만 하고
        집계는 하지 않는다(Repository는 SQL만, 집계는 Service — CLAUDE.md §4/§8).
        """
        stmt = (
            select(
                Segment.duration_sec,
                Segment.sample_rate,
                Segment.file_size,
                Segment.format,
                Segment.is_labeled,
                Dataset.project_id,
                Project.name.label("project_name"),
            )
            .join(Dataset, Segment.dataset_id == Dataset.id)
            .join(Project, Dataset.project_id == Project.id)
        )
        if project_id is not None:
            stmt = stmt.where(Dataset.project_id == project_id)
        return [dict(row._mapping) for row in self.db.execute(stmt).all()]
