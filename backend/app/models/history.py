"""UploadHistory 테이블 — 업로드 이력 (05 §3.6).

누가/언제/무슨 파일을 올렸나. ProcessingHistory는 Job이 겸하므로 여기엔 두지 않는다.
대시보드 "최근 업로드"의 출처.
"""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class UploadHistory(Base, TimestampMixin):
    __tablename__ = "upload_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    project: Mapped["Project"] = relationship(  # noqa: F821
        back_populates="upload_histories"
    )
