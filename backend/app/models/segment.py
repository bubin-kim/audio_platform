"""Segment 테이블 — 커팅 조각 1개 = 메타데이터 1행 (05 §3.3).

labels(JSON) 한 칸이 재사용성의 핵심: 도메인이 뭐가 오든 라벨을 여기 담는다.
테이블 구조는 도메인이 바뀌어도 그대로다(P1).
"""

from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class Segment(Base, TimestampMixin):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 이 세그먼트가 나온 원본(재현성·재처리 추적). 선택적.
    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_files.id", ondelete="SET NULL"), nullable=True, index=True
    )

    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    # Storage 인터페이스 기준 논리 경로(로컬/Drive 무관).
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # --- 자동 추출 메타데이터 ---
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, nullable=False)
    # 압축 포맷(mp3 등)은 bit_depth가 의미 없음 → nullable.
    bit_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    # 원본에서 잘린 시작 위치(재현성).
    source_start_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # --- 라벨 (도메인별) ---
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_labeled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    dataset: Mapped["Dataset"] = relationship(  # noqa: F821
        back_populates="segments"
    )
    source_file: Mapped["SourceFile | None"] = relationship(  # noqa: F821
        back_populates="segments"
    )
