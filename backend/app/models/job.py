"""Job 테이블 — 비동기 작업 = 재현성 + 진행률 (05 §3.5).

02 아키텍처의 백그라운드 커팅을 1급 객체로 둔다. Job.params/status/finished_at이
곧 "무엇을 언제 어떤 설정으로 처리했나"의 기록 → 별도 ProcessingHistory를 두지 않는다(05 §3.6).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

# 허용값 (문자열 저장 — 방언 종속 회피).
JOB_TYPES = ("cutting", "export")
JOB_STATUSES = ("queued", "running", "done", "failed")


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued"
    )

    # 진행률 = progress / total_items. total은 시작 후 확정될 수 있어 nullable.
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_items: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 실행 당시 설정(전략·파라미터·common_labels 등) → 재현성.
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # export Job 완료 시 결과물(CSV) 논리 경로.
    result_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    dataset: Mapped["Dataset"] = relationship(  # noqa: F821
        back_populates="jobs"
    )
