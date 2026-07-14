"""CachedDriveStorage 테스트 (DP-M3, docs/13 §4) — 실제 Drive 불필요(MockTransport).

핵심 계약: Drive가 진실 원천 / 캐시 히트 시 Drive 호출 0회 / 저장·읽기 실패는
재시도(3회) 후 예외로 드러남 / LRU 상한 초과 시 오래된 파일부터 제거.
"""

from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.storage import build_storage
from app.storage.cached_drive import CachedDriveStorage
from app.storage.drive import GoogleDriveStorage
from tests.test_drive_storage import ROOT_ID, _DriveRecorder


class _FailFirst:
    """Drive API 요청(토큰 제외)을 처음 n회 지정 상태코드로 실패시키는 래퍼."""

    def __init__(self, inner: _DriveRecorder, failures: int, status: int = 500) -> None:
        self._inner = inner
        self.remaining = failures
        self._status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if "oauth2" not in str(request.url) and self.remaining > 0:
            self.remaining -= 1
            return httpx.Response(self._status, json={"error": "simulated"})
        return self._inner(request)


def _cached(
    tmp_path: Path,
    handler,  # noqa: ANN001
    *,
    cache_max_mb: float = 10.0,
) -> tuple[CachedDriveStorage, list[float]]:
    drive = GoogleDriveStorage(
        client_id="cid", client_secret="cs", refresh_token="rt",
        root_folder_id=ROOT_ID, timeout_sec=5.0,
        transport=httpx.MockTransport(handler),
    )
    sleeps: list[float] = []
    storage = CachedDriveStorage(
        drive=drive, cache_dir=tmp_path / "cache",
        cache_max_mb=cache_max_mb, sleep=sleeps.append,
    )
    return storage, sleeps


def test_save_uploads_to_drive_and_caches(tmp_path: Path) -> None:
    rec = _DriveRecorder()
    st, _ = _cached(tmp_path, rec)
    st.save("segments/1/a.wav", b"RIFFxxxx")
    assert rec.contents  # Drive에 올라감 (진실 원천)
    assert (tmp_path / "cache/segments/1/a.wav").read_bytes() == b"RIFFxxxx"


def test_read_hits_cache_without_drive_calls(tmp_path: Path) -> None:
    rec = _DriveRecorder()
    st, _ = _cached(tmp_path, rec)
    st.save("segments/1/a.wav", b"RIFFxxxx")
    before = len(rec.requests)
    assert st.read("segments/1/a.wav") == b"RIFFxxxx"
    assert st.local_path("segments/1/a.wav").is_file()
    assert st.exists("segments/1/a.wav") is True
    assert len(rec.requests) == before  # 전부 캐시 히트 — Drive 호출 0회


def test_read_miss_downloads_then_caches(tmp_path: Path) -> None:
    rec = _DriveRecorder()
    seeder, _ = _cached(tmp_path / "seed", rec)
    seeder.save("segments/1/a.wav", b"RIFFxxxx")  # Drive에만 존재한다고 가정

    fresh, _ = _cached(tmp_path / "fresh", rec)  # 캐시 비어 있음(컨테이너 재시작 상황)
    assert fresh.read("segments/1/a.wav") == b"RIFFxxxx"  # Drive에서 다운로드
    before = len(rec.requests)
    assert fresh.read("segments/1/a.wav") == b"RIFFxxxx"  # 두 번째는 캐시
    assert len(rec.requests) == before


def test_retry_recovers_after_transient_5xx(tmp_path: Path) -> None:
    flaky = _FailFirst(_DriveRecorder(), failures=2)
    st, sleeps = _cached(tmp_path, flaky)
    st.save("segments/1/a.wav", b"x")  # 2회 실패 후 성공해야 함
    assert len(sleeps) == 2  # 백오프 2회


def test_retry_gives_up_and_raises(tmp_path: Path) -> None:
    flaky = _FailFirst(_DriveRecorder(), failures=99)
    st, sleeps = _cached(tmp_path, flaky)
    with pytest.raises(httpx.HTTPStatusError):
        st.save("segments/1/a.wav", b"x")
    assert len(sleeps) == 3  # 재시도 3회 후 포기 (docs/13 §4)


def test_non_retryable_4xx_raises_immediately(tmp_path: Path) -> None:
    flaky = _FailFirst(_DriveRecorder(), failures=99, status=403)
    st, sleeps = _cached(tmp_path, flaky)
    with pytest.raises(httpx.HTTPStatusError):
        st.save("segments/1/a.wav", b"x")
    assert sleeps == []  # 권한 오류는 재시도해봐야 소용없다


def test_lru_evicts_oldest_when_over_limit(tmp_path: Path) -> None:
    rec = _DriveRecorder()
    limit_bytes = 250
    st, _ = _cached(tmp_path, rec, cache_max_mb=limit_bytes / (1024 * 1024))
    st.save("segments/1/a.wav", b"a" * 100)
    st.save("segments/1/b.wav", b"b" * 100)
    st.read("segments/1/a.wav")  # a를 최근 사용으로 갱신
    st.save("segments/1/c.wav", b"c" * 100)  # 300B > 250B → LRU(b) 제거
    cache = tmp_path / "cache/segments/1"
    assert (cache / "a.wav").exists()
    assert not (cache / "b.wav").exists()
    assert (cache / "c.wav").exists()
    # 캐시에서 사라졌어도 Drive(진실 원천)에서 다시 읽힌다
    assert st.read("segments/1/b.wav") == b"b" * 100


def test_delete_removes_drive_and_cache(tmp_path: Path) -> None:
    rec = _DriveRecorder()
    st, _ = _cached(tmp_path, rec)
    st.save("segments/1/a.wav", b"x")
    st.delete("segments/1/a.wav")
    assert not (tmp_path / "cache/segments/1/a.wav").exists()
    assert [r for r in rec.requests if r.method == "DELETE"]


# --- build_storage 모드 분기 (docs/13 §4) ---

def _settings(**overrides) -> Settings:  # noqa: ANN003
    base = dict(
        data_dir="/tmp/x", storage_mode="local",
        google_oauth_client_id="", google_oauth_client_secret="",
        google_oauth_refresh_token="", drive_root_folder_id="",
    )
    base.update(overrides)
    return Settings(**base)


def test_drive_primary_without_tokens_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="drive_primary"):
        build_storage(_settings(storage_mode="drive_primary"))


def test_drive_primary_with_tokens_builds_cached(tmp_path: Path) -> None:
    st = build_storage(_settings(
        storage_mode="drive_primary",
        google_oauth_client_id="a", google_oauth_client_secret="b",
        google_oauth_refresh_token="c", drive_root_folder_id="d",
        cache_dir=str(tmp_path / "c"),
    ))
    assert isinstance(st, CachedDriveStorage)


def test_unknown_mode_rejected() -> None:
    with pytest.raises(ValueError, match="STORAGE_MODE"):
        build_storage(_settings(storage_mode="s3"))
