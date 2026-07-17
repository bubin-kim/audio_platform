"""Stats(대시보드) 입출력 스키마 (Pydantic) — 06_API.md §9."""

from datetime import datetime

from pydantic import BaseModel


class UploadProgress(BaseModel):
    current_sec: float
    target_sec: float | None
    ratio: float | None


class LabelingProgress(BaseModel):
    labeled: int
    total: int
    ratio: float | None


class RecentUpload(BaseModel):
    filename: str
    uploaded_at: datetime
    file_size: int | None
    uploaded_by: str | None = None


class CollectionProgress(BaseModel):
    """수집 진행률(세그먼트 개수 기준, docs/15). target 없으면 ratio는 null."""

    collected: int
    target: int | None
    ratio: float | None


class ProjectStats(BaseModel):
    project_id: int
    name: str
    segment_count: int
    duration_sec: float


class StatsResponse(BaseModel):
    total_segments: int
    total_duration_sec: float
    total_size_bytes: int
    avg_duration_sec: float
    sample_rate_distribution: dict[str, int]
    format_distribution: dict[str, int]
    upload_progress: UploadProgress
    collection_progress: CollectionProgress
    labeling_progress: LabelingProgress
    recent_uploads: list[RecentUpload]
    # project_id로 범위를 좁힌 조회에서는 None(전체 조회일 때만 채운다, 06_API.md §9).
    per_project: list[ProjectStats] | None = None
