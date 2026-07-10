"""Dataset 테이블 — 버전 있는 데이터 묶음 (05 §3.2).

하나의 Project는 여러 Dataset을 가진다(v1 초기수집, v2 재수집 등).
Segment·SourceFile·Job이 이 아래에 매달린다.
"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

# status 허용값 (문자열로 저장 — DB enum 방언 종속 회피, 05 §5).
DATASET_STATUSES = ("collecting", "processing", "ready")


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="collecting"
    )

    project: Mapped["Project"] = relationship(  # noqa: F821
        back_populates="datasets"
    )
    segments: Mapped[list["Segment"]] = relationship(  # noqa: F821
        back_populates="dataset", cascade="all, delete-orphan"
    )
    source_files: Mapped[list["SourceFile"]] = relationship(  # noqa: F821
        back_populates="dataset", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(  # noqa: F821
        back_populates="dataset", cascade="all, delete-orphan"
    )
