"""Storage 패키지 — 저장소 구현 선택은 여기 한 곳에서.

Service는 get_storage()가 무엇을 돌려주는지 모른다(P3).
Drive 미설정 → LocalStorage / 설정 → MirrorStorage(로컬 주 + Drive 비동기 미러, docs/09).
"""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.storage.base import StorageBackend
from app.storage.cached_drive import CachedDriveStorage
from app.storage.drive import GoogleDriveStorage
from app.storage.local import LocalStorage
from app.storage.mirror import MirrorStorage


def _drive_from(settings: Settings) -> GoogleDriveStorage:
    return GoogleDriveStorage(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        refresh_token=settings.google_oauth_refresh_token,
        root_folder_id=settings.drive_root_folder_id,
        timeout_sec=settings.drive_timeout_sec,
    )


def build_storage(settings: Settings) -> StorageBackend:
    """설정에 맞는 저장소 조립 (테스트에서 Settings를 직접 넣어 분기 검증)."""
    if settings.storage_mode == "drive_primary":
        # 배포 모드(docs/13 §4): Drive가 진실 원천. 설정이 없으면 시작을 거부한다
        # (조용히 로컬로 폴백하면 배포 환경에서 데이터가 컨테이너와 함께 증발한다).
        if not settings.drive_enabled:
            raise ValueError(
                "STORAGE_MODE=drive_primary에는 Drive OAuth 4종"
                "(GOOGLE_OAUTH_*·DRIVE_ROOT_FOLDER_ID) 설정이 필요합니다 (docs/13 §4)."
            )
        return CachedDriveStorage(
            drive=_drive_from(settings),
            cache_dir=settings.cache_dir,
            cache_max_mb=settings.cache_max_mb,
        )
    if settings.storage_mode != "local":
        raise ValueError(f"알 수 없는 STORAGE_MODE='{settings.storage_mode}' (local | drive_primary)")

    local = LocalStorage(root=settings.data_dir)
    if not settings.drive_enabled:
        return local
    return MirrorStorage(
        local=local, mirror=_drive_from(settings), prefixes=settings.drive_mirror_prefixes
    )


@lru_cache
def get_storage() -> StorageBackend:
    """앱 전역 저장소 싱글턴."""
    return build_storage(get_settings())


__all__ = ["StorageBackend", "get_storage", "build_storage"]
