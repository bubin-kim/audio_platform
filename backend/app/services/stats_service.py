"""Stats 서비스 — 대시보드 집계 (05_database.md §4, 06_API.md §9).

Repository가 준 평면 행(Segment+Project 조인 결과)을 pandas로 집계한다
(CLAUDE.md §3 기술 스택). Service는 SQL을 직접 쓰지 않는다(P3).

upload_progress.target_sec: 프로젝트 범위 조회는 그 프로젝트의 target_duration_sec을
그대로 쓴다. 전체 조회는 target_duration_sec이 설정된 모든 프로젝트의 합을 쓴다
(도메인 분기 없이 일반화한 값 — 06_API.md에 전체 조회 시의 합산 규칙이 명시돼 있지
않아 내린 판단이므로, 다르게 정의하고 싶다면 알려달라).
"""

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.project import Project
from app.repositories.history_repo import UploadHistoryRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.segment_repo import SegmentRepository
from app.schemas.stats import (
    LabelingProgress,
    ProjectStats,
    RecentUpload,
    StatsResponse,
    UploadProgress,
)

_COLUMNS = [
    "duration_sec",
    "sample_rate",
    "file_size",
    "format",
    "is_labeled",
    "project_id",
    "project_name",
]


class StatsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.segment_repo = SegmentRepository(db)
        self.history_repo = UploadHistoryRepository(db)

    def get_stats(self, *, project_id: int | None = None) -> StatsResponse:
        if project_id is not None and self.project_repo.get(project_id) is None:
            raise NotFoundError(f"Project {project_id}를 찾을 수 없습니다.")

        df = pd.DataFrame(self.segment_repo.stats_rows(project_id), columns=_COLUMNS)
        total_segments = len(df)
        total_duration_sec = float(df["duration_sec"].sum())
        total_size_bytes = int(df["file_size"].sum())
        avg_duration_sec = float(df["duration_sec"].mean()) if total_segments else 0.0
        labeled = int(df["is_labeled"].sum()) if total_segments else 0

        per_project: list[ProjectStats] | None = None
        if project_id is not None:
            target_sec = self.project_repo.get(project_id).target_duration_sec
        else:
            projects = self.project_repo.list_all()
            targets = [p.target_duration_sec for p in projects if p.target_duration_sec]
            target_sec = sum(targets) if targets else None
            per_project = self._per_project(df, projects)

        return StatsResponse(
            total_segments=total_segments,
            total_duration_sec=total_duration_sec,
            total_size_bytes=total_size_bytes,
            avg_duration_sec=avg_duration_sec,
            sample_rate_distribution=_value_counts(df, "sample_rate"),
            format_distribution=_value_counts(df, "format"),
            upload_progress=UploadProgress(
                current_sec=total_duration_sec,
                target_sec=target_sec,
                ratio=(total_duration_sec / target_sec) if target_sec else None,
            ),
            labeling_progress=LabelingProgress(
                labeled=labeled,
                total=total_segments,
                ratio=(labeled / total_segments) if total_segments else None,
            ),
            recent_uploads=[
                RecentUpload(
                    filename=h.filename,
                    uploaded_at=h.created_at,
                    file_size=h.file_size,
                )
                for h in self.history_repo.recent(limit=10, project_id=project_id)
            ],
            per_project=per_project,
        )

    def _per_project(
        self, df: pd.DataFrame, projects: list[Project]
    ) -> list[ProjectStats]:
        counts: dict[int, Any] = {}
        durations: dict[int, Any] = {}
        if not df.empty:
            grouped = df.groupby("project_id")["duration_sec"].agg(["size", "sum"])
            counts = grouped["size"].to_dict()
            durations = grouped["sum"].to_dict()
        return [
            ProjectStats(
                project_id=p.id,
                name=p.name,
                segment_count=int(counts.get(p.id, 0)),
                duration_sec=float(durations.get(p.id, 0.0)),
            )
            for p in projects
        ]


def _value_counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    if df.empty:
        return {}
    return {str(k): int(v) for k, v in df[column].value_counts().items()}
