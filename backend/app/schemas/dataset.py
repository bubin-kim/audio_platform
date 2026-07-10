"""Dataset 입출력 스키마 (Pydantic) — 06_API.md §4."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="v1", max_length=50)


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    version: str
    status: str
    created_at: datetime
