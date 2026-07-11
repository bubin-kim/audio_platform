"""MirrorStorage — 로컬 주 저장소 + Drive 비동기 미러 (V2-3, docs/09 §3).

StorageBackend를 그대로 구현하므로 Service·worker는 이 클래스의 존재를 모른다(P3).
- 쓰기: 로컬 완료(동기) 후, 미러 prefix에 해당하면 데몬 스레드로 미러 업로드.
- 읽기(read/local_path/exists/list): 로컬만 — Drive를 절대 조회하지 않는다.
- 삭제: 로컬 삭제 + 미러 대상이면 비동기 미러 삭제.
- 미러 실패는 로그만 남기고 본 흐름을 깨지 않는다 (로컬이 원본, 재export로 재생성 가능).
"""

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _spawn(target: Callable[..., None], **kwargs: Any) -> None:
    """데몬 스레드 실행. 테스트에서 동기 실행으로 몽키패치한다(notion과 동일 패턴)."""
    threading.Thread(target=target, kwargs=kwargs, daemon=True).start()


class MirrorStorage(StorageBackend):
    def __init__(
        self,
        *,
        local: StorageBackend,
        mirror: StorageBackend,
        prefixes: list[str],
    ) -> None:
        self._local = local
        self._mirror = mirror
        # "exports" → "exports/" 형태로 정규화(경계 명확화)
        self._prefixes = tuple(p.rstrip("/") + "/" for p in prefixes)

    def _should_mirror(self, path: str) -> bool:
        return path.lstrip("/").startswith(self._prefixes)

    # --- 쓰기: 로컬 동기 + 미러 비동기 ---

    def save(self, path: str, data: bytes) -> str:
        logical = self._local.save(path, data)
        self._queue_mirror_upload(logical)
        return logical

    def save_from_path(self, path: str, source: Path) -> str:
        logical = self._local.save_from_path(path, source)
        self._queue_mirror_upload(logical)
        return logical

    def _queue_mirror_upload(self, logical: str) -> None:
        if self._should_mirror(logical):
            _spawn(self._mirror_upload, logical=logical)

    def _mirror_upload(self, logical: str) -> None:
        """스레드 본체: 로컬의 안정된 사본을 읽어 미러에 올린다. 실패는 로그만."""
        try:
            # 원본 바이트를 스레드에 넘기지 않고 로컬에서 다시 읽는다
            # (save_from_path의 source가 임시파일이라 스레드 시점엔 사라질 수 있음).
            data = self._local.read(logical)
            self._mirror.save(logical, data)
            logger.info("drive 미러 업로드 완료: %s", logical)
        except Exception:  # noqa: BLE001 - 미러 실패가 본 흐름을 깨선 안 됨
            logger.exception("drive 미러 업로드 실패: %s", logical)

    # --- 삭제: 로컬 + 미러 ---

    def delete(self, path: str) -> None:
        self._local.delete(path)
        if self._should_mirror(path):
            _spawn(self._mirror_delete, logical=path)

    def _mirror_delete(self, logical: str) -> None:
        try:
            self._mirror.delete(logical)
            logger.info("drive 미러 삭제 완료: %s", logical)
        except Exception:  # noqa: BLE001
            logger.exception("drive 미러 삭제 실패: %s", logical)

    # --- 읽기 계열: 항상 로컬 ---

    def read(self, path: str) -> bytes:
        return self._local.read(path)

    def local_path(self, path: str) -> Path:
        return self._local.local_path(path)

    def exists(self, path: str) -> bool:
        return self._local.exists(path)

    def list(self, prefix: str = "") -> list[str]:
        return self._local.list(prefix)
