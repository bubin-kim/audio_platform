"""공통 스키마 — 목록 페이지·에러 (06_API.md §1)."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """목록 응답 공통 형태."""

    items: list[T]
    total: int


class ErrorResponse(BaseModel):
    """공통 에러 응답."""

    detail: str
    code: str | None = None
