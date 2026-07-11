"""Storage 패키지 — 저장소 구현 선택은 여기 한 곳에서.

Service는 get_storage()가 무엇을 돌려주는지 모른다(P3).
Drive 미설정 → LocalStorage / 설정 → MirrorStorage(로컬 주 + Drive 비동기 미러, docs/09).
"""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.storage.base import StorageBackend
from app.storage.drive import GoogleDriveStorage
from app.storage.local import LocalStorage
from app.storage.mirror import MirrorStorage


def build_storage(settings: Settings) -> StorageBackend:
    """설정에 맞는 저장소 조립 (테스트에서 Settings를 직접 넣어 분기 검증)."""
    local = LocalStorage(root=settings.data_dir)
    if not settings.drive_enabled:
        return local
    drive = GoogleDriveStorage(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        refresh_token=settings.google_oauth_refresh_token,
        root_folder_id=settings.drive_root_folder_id,
        timeout_sec=settings.drive_timeout_sec,
    )
    return MirrorStorage(
        local=local, mirror=drive, prefixes=settings.drive_mirror_prefixes
    )


@lru_cache
def get_storage() -> StorageBackend:
    """앱 전역 저장소 싱글턴."""
    return build_storage(get_settings())


__all__ = ["StorageBackend", "get_storage", "build_storage"]
