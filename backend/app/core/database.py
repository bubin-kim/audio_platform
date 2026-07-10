"""DB 엔진·세션 설정 (SQLAlchemy 2.0).

Repository Layer가 이 세션을 통해서만 DB에 접근한다. Service는 DB 종류를 모른다(P3).
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

# SQLite는 기본이 단일 스레드 체크 → FastAPI 멀티스레드 대응으로 해제.
# PostgreSQL 전환 시 이 인자는 무시되도록 조건 처리.
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)

if _is_sqlite:
    # SQLite는 연결마다 FK 제약이 꺼져 있다 → ondelete=CASCADE가 동작하도록 켠다.
    # (PostgreSQL은 항상 켜져 있으므로 이 리스너는 SQLite에서만 등록.)
    @event.listens_for(Engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스. models/ 의 테이블들이 이걸 상속한다."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 의존성: 요청당 세션 하나를 열고 끝나면 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
