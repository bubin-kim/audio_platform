"""Repository 공통 베이스 (P3).

Repository는 ORM 접근을 감싸 Service가 SQL을 모르게 한다(CLAUDE.md §8).
트랜잭션 경계(commit)는 Service가 잡는다. 여기서는 add+flush(ID 확보)까지만.
"""

from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """모델별 공통 CRUD. 각 repo는 model 클래스만 지정하면 된다."""

    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, obj_id: int) -> ModelT | None:
        return self.db.get(self.model, obj_id)

    def list(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        stmt = (
            select(self.model)
            .order_by(self.model.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return self.db.scalar(select(func.count()).select_from(self.model)) or 0

    def add(self, obj: ModelT) -> ModelT:
        """추가 후 flush해 PK를 채운다(commit은 Service가)."""
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.db.delete(obj)
        self.db.flush()
