"""Job / Processing 입출력 스키마 (Pydantic) — 06_API.md §6, §7."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProcessRequest(BaseModel):
    """커팅 시작 요청. 바디 없이 호출하면 Dataset의 전체 SourceFile을 기본 설정으로 처리."""

    source_file_ids: list[int] | None = None
    params_override: dict[str, Any] | None = None
    common_labels: dict[str, Any] = {}


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    type: str
    status: str
    progress: int
    total_items: int | None
    params: dict[str, Any]
    error_msg: str | None
    result_path: str | None
    started_at: datetime | None
    finished_at: datetime | None
