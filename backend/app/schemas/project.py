"""Project 입출력 스키마 (Pydantic) — 06_API.md §3.

models(ORM)와 절대 섞지 않는다(CLAUDE.md §4). 이 파일은 Pydantic만.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LabelType = Literal["string", "number", "enum", "bool"]


class LabelFieldSchema(BaseModel):
    """label_schema의 한 필드 정의. Project가 요구하는 라벨의 형태(05 §2)."""

    key: str
    type: LabelType
    required: bool = False
    options: list[str] | None = None  # type=="enum"일 때 필수

    @model_validator(mode="after")
    def _check_enum_options(self) -> "LabelFieldSchema":
        if self.type == "enum" and not self.options:
            raise ValueError(f"enum 필드 '{self.key}'에는 options가 필요합니다.")
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str | None = None
    cutting_mode: str
    cutting_params: dict[str, Any] = Field(default_factory=dict)
    naming_pattern: str = Field(min_length=1)
    label_schema: list[LabelFieldSchema] = Field(default_factory=list)
    target_duration_sec: float | None = Field(default=None, gt=0)


class ProjectUpdate(BaseModel):
    """부분 수정 — 모든 필드 optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = None
    cutting_mode: str | None = None
    cutting_params: dict[str, Any] | None = None
    naming_pattern: str | None = Field(default=None, min_length=1)
    label_schema: list[LabelFieldSchema] | None = None
    target_duration_sec: float | None = Field(default=None, gt=0)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: str | None
    cutting_mode: str
    cutting_params: dict[str, Any]
    naming_pattern: str
    label_schema: list[LabelFieldSchema]
    target_duration_sec: float | None
    created_at: datetime
