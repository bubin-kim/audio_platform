"""Project 입출력 스키마 (Pydantic) — 06_API.md §3.

models(ORM)와 절대 섞지 않는다(CLAUDE.md §4). 이 파일은 Pydantic만.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LabelType = Literal["string", "number", "enum", "bool"]


class LabelFieldSchema(BaseModel):
    """label_schema의 한 필드 정의. Project가 요구하는 라벨의 형태(05 §2).

    검증 없는 기본형 — **읽기(ProjectRead)용**. C1 검증 도입 전에 저장된
    레거시 행(예: options=[''])도 조회는 500 없이 그대로 직렬화돼야 한다.
    입력 검증은 LabelFieldSchemaIn이 담당한다 (쓰기는 엄격, 읽기는 관대).
    """

    key: str
    type: LabelType
    required: bool = False
    options: list[str] | None = None  # type=="enum"일 때 필수


class LabelFieldSchemaIn(LabelFieldSchema):
    """생성/수정 입력용 — 빈 enum 방어 검증 포함 (docs/12 C1)."""

    @model_validator(mode="after")
    def _check_enum_options(self) -> "LabelFieldSchemaIn":
        if self.type != "enum":
            return self
        # 빈 문자열/공백 옵션 거부 + 정규화 (docs/12 C1 — options:[''] 실사고 방어)
        cleaned = [o.strip() for o in (self.options or []) if o and o.strip()]
        if not cleaned:
            raise ValueError(
                f"enum 필드 '{self.key}'에는 비어 있지 않은 options가 최소 1개 필요합니다."
            )
        if len(set(cleaned)) != len(cleaned):
            raise ValueError(f"enum 필드 '{self.key}'의 options에 중복이 있습니다.")
        self.options = cleaned
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str | None = None
    cutting_mode: str
    cutting_params: dict[str, Any] = Field(default_factory=dict)
    naming_pattern: str = Field(min_length=1)
    label_schema: list[LabelFieldSchemaIn] = Field(default_factory=list)
    target_duration_sec: float | None = Field(default=None, gt=0)
    expected_segments_per_source: int | None = Field(default=None, ge=1)
    target_segment_count: int | None = Field(default=None, ge=1)


class ProjectUpdate(BaseModel):
    """부분 수정 — 모든 필드 optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = None
    cutting_mode: str | None = None
    cutting_params: dict[str, Any] | None = None
    naming_pattern: str | None = Field(default=None, min_length=1)
    label_schema: list[LabelFieldSchemaIn] | None = None
    target_duration_sec: float | None = Field(default=None, gt=0)
    expected_segments_per_source: int | None = Field(default=None, ge=1)
    target_segment_count: int | None = Field(default=None, ge=1)


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
    expected_segments_per_source: int | None
    target_segment_count: int | None
    created_at: datetime
