"""Segment 입출력 스키마 (Pydantic) — 06_API.md §4.2, §8."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WaveformRead(BaseModel):
    """세그먼트 미니 파형 데이터 (06_API.md §4.5).

    peaks는 풀스케일(1.0) 기준 절대 피크 — 세그먼트 간 높이 비교 가능.
    """

    segment_id: int
    duration_sec: float
    peaks: list[float]


class LabelUpdate(BaseModel):
    """개별 세그먼트 라벨 수정 요청 (06_API.md §8 — 예외 보정용).

    기존 labels 위에 부분 덮어쓰기(merge)된다. 병합 결과가 label_schema로 검증된다.
    """

    labels: dict[str, Any]


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    filename: str
    storage_path: str
    duration_sec: float
    sample_rate: int
    channels: int
    bit_depth: int | None
    file_size: int
    format: str
    source_start_sec: float
    labels: dict[str, Any]
    is_labeled: bool
    created_at: datetime
