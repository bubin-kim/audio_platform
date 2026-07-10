"""API 공통 의존성.

라우트가 주입받는 공통 자원(DB 세션·Storage)을 모은다.
Depends로 주입하므로 테스트에서 손쉽게 교체(override)할 수 있다.
"""

from app.core.database import get_db
from app.storage import get_storage
from app.storage.base import StorageBackend


def get_storage_dep() -> StorageBackend:
    """Storage 백엔드 의존성. 기본은 설정에 따른 구현체(MVP: LocalStorage)."""
    return get_storage()


__all__ = ["get_db", "get_storage_dep", "StorageBackend"]
