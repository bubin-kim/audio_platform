"""Storage 패키지 — 저장소 구현 선택은 여기 한 곳에서.

Service는 get_storage()가 무엇을 돌려주는지 모른다(P3). MVP는 Local, V2는 Drive.
"""

from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorage


@lru_cache
def get_storage() -> StorageBackend:
    """설정에 맞는 저장소 백엔드를 반환한다(MVP: LocalStorage, root=data_dir)."""
    settings = get_settings()
    return LocalStorage(root=settings.data_dir)


__all__ = ["StorageBackend", "get_storage"]
