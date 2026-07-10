"""ORM 공통 요소 (믹스인·헬퍼).

모든 테이블이 공유하는 created_at 등을 여기에 모은다. Base 자체는 core/database.py 에 있다.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """timezone-aware UTC 현재 시각. (datetime.utcnow는 3.12에서 deprecated)"""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """생성 시각 컬럼을 제공하는 믹스인."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
