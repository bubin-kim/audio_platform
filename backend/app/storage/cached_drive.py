"""CachedDriveStorage — Drive 주 저장소 + 로컬 LRU 읽기 캐시 (DP-M3, docs/13 §4).

drive_primary 모드의 저장소: **진실 원천은 Drive**, 로컬 디스크는 캐시일 뿐이다
(컨테이너 재시작으로 캐시가 사라져도 무해 — 다시 내려받으면 된다).

미러(V2-3)와의 결정적 차이: 여기서 Drive 호출 실패는 숨기지 않는다.
재시도(지수 백오프 3회, 429/5xx·네트워크 오류 대상) 후에도 실패하면 예외를
올려서 Job failed로 드러낸다 — 주 저장소의 실패는 본 흐름의 실패다(docs/13 §4).
"""

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from app.storage.base import StorageBackend
from app.storage.drive import GoogleDriveStorage

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_RETRY_DELAYS_SEC = (0.5, 1.0, 2.0)  # 재시도 3회 (총 시도 4회)


class CachedDriveStorage(StorageBackend):
    def __init__(
        self,
        *,
        drive: GoogleDriveStorage,
        cache_dir: Path | str,
        cache_max_mb: float,
        sleep: Callable[[float], None] = time.sleep,  # 테스트에서 대기 제거용
    ) -> None:
        self._drive = drive
        self._cache_root = Path(cache_dir)
        self._cache_root.mkdir(parents=True, exist_ok=True)
        self._max_bytes = int(cache_max_mb * 1024 * 1024)
        self._sleep = sleep

    # --- 재시도 래퍼 ---

    def _with_retry(self, op_name: str, fn: Callable[[], object]) -> object:
        for attempt in range(len(_RETRY_DELAYS_SEC) + 1):
            try:
                return fn()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                retryable = isinstance(exc, httpx.TransportError) or (
                    exc.response.status_code in _RETRYABLE_STATUS
                )
                if not retryable or attempt == len(_RETRY_DELAYS_SEC):
                    raise
                delay = _RETRY_DELAYS_SEC[attempt]
                logger.warning(
                    "Drive %s 실패(%s) — %.1fs 후 재시도 (%d/%d)",
                    op_name, exc, delay, attempt + 1, len(_RETRY_DELAYS_SEC),
                )
                self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    # --- 캐시 ---

    def _cache_path(self, path: str) -> Path:
        return self._cache_root / path.lstrip("/")

    def _cache_put(self, path: str, data: bytes) -> Path:
        target = self._cache_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self._evict_lru()
        return target

    def _evict_lru(self) -> None:
        """캐시 총량이 상한을 넘으면 오래 안 쓴 파일부터 지운다(mtime 기준 LRU)."""
        files = [p for p in self._cache_root.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        if total <= self._max_bytes:
            return
        for p in sorted(files, key=lambda f: f.stat().st_mtime):
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
            if total <= self._max_bytes:
                break

    def _cache_hit(self, path: str) -> Path | None:
        p = self._cache_path(path)
        if p.is_file():
            os.utime(p, None)  # LRU 갱신: 최근 사용 표시
            return p
        return None

    # --- StorageBackend 구현 ---

    def save(self, path: str, data: bytes) -> str:
        logical = str(self._with_retry("save", lambda: self._drive.save(path, data)))
        self._cache_put(logical, data)
        return logical

    def save_from_path(self, path: str, source: Path) -> str:
        return self.save(path, Path(source).read_bytes())

    def read(self, path: str) -> bytes:
        hit = self._cache_hit(path)
        if hit is not None:
            return hit.read_bytes()
        data = self._with_retry("read", lambda: self._drive.read(path))
        assert isinstance(data, bytes)
        self._cache_put(path, data)
        return data

    def local_path(self, path: str) -> Path:
        """오디오 라이브러리용 실제 경로 — 캐시에 내려받아 그 경로를 준다."""
        hit = self._cache_hit(path)
        if hit is not None:
            return hit
        data = self._with_retry("read", lambda: self._drive.read(path))
        assert isinstance(data, bytes)
        return self._cache_put(path, data)

    def exists(self, path: str) -> bool:
        if self._cache_hit(path) is not None:
            return True
        return bool(self._with_retry("exists", lambda: self._drive.exists(path)))

    def delete(self, path: str) -> None:
        self._with_retry("delete", lambda: self._drive.delete(path))
        self._cache_path(path).unlink(missing_ok=True)

    def list(self, prefix: str = "") -> list[str]:
        raise NotImplementedError("코어 흐름 미사용 — 필요해지면 구현 (docs/13 §4)")
