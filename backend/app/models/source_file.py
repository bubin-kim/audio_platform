"""SourceFile 테이블 — 업로드된 원본 추적 (05 §3.4).

어떤 원본에서 세그먼트들이 나왔는지 기록 → 재현성·재처리에 필요.
업로드 시 생성되고, 커팅 Job이 이 원본을 읽어 Segment를 만든다.
"""

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class SourceFile(Base, TimestampMixin):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # 원본 총 길이·기본 메타(업로드 시 헤더에서 추출).
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bit_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)

    dataset: Mapped["Dataset"] = relationship(  # noqa: F821
        back_populates="source_files"
    )
    segments: Mapped[list["Segment"]] = relationship(  # noqa: F821
        back_populates="source_file"
    )
