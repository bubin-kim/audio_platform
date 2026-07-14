"""공용 액세스 토큰 가드 테스트 (docs/13 §6, 06_API.md §2.5).

핵심 계약: ACCESS_TOKEN 미설정이면 전부 통과(기존 동작), 설정 시 /api/*는 Bearer 필수,
미디어 URL(오디오/파형/다운로드)만 ?token= 쿼리 허용, /health는 항상 무인증.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.conftest import upload_file

TOKEN = "lab-secret-token"


@pytest.fixture
def auth_on() -> Iterator[str]:
    """토큰을 켰다가 테스트 후 반드시 끈다 (다른 테스트에 영향 금지)."""
    settings = get_settings()
    settings.access_token = TOKEN
    try:
        yield TOKEN
    finally:
        settings.access_token = ""


def _bearer(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_disabled_token_passes_everything(client: TestClient) -> None:
    """미설정(기본) — 인증 없이 기존과 동일하게 동작한다."""
    assert client.get("/api/projects").status_code == 200


def test_enabled_requires_bearer(client: TestClient, auth_on: str) -> None:
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects", headers=_bearer("wrong")).status_code == 401
    r = client.get("/api/projects", headers=_bearer())
    assert r.status_code == 200


def test_health_and_preflight_are_open(client: TestClient, auth_on: str) -> None:
    assert client.get("/health").status_code == 200
    # CORS preflight는 브라우저가 헤더를 못 붙이는 단계라 통과해야 한다.
    r = client.options("/api/projects", headers={"Origin": "http://x", "Access-Control-Request-Method": "GET"})
    assert r.status_code != 401


def test_query_token_only_for_media(
    client: TestClient, make_wav: Callable[..., Path], auth_on: str
) -> None:
    # 데이터 준비는 Bearer로 (프로젝트 생성 → 업로드 → 커팅)
    payload = {
        "name": "인증검증",
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [],
    }
    client.headers.update(_bearer())
    pid = client.post("/api/projects", json=payload).json()["id"]
    wav = make_wav(duration_sec=1.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    client.post(f"/api/datasets/{ds_id}/process", json={})
    seg = client.get(f"/api/datasets/{ds_id}/segments").json()["items"][0]
    client.headers.pop("Authorization")

    # 미디어 URL: 쿼리 토큰 허용 (올바른 토큰만)
    assert client.get(f"/api/segments/{seg['id']}/audio?token={TOKEN}").status_code == 200
    assert client.get(f"/api/segments/{seg['id']}/audio?token=wrong").status_code == 401
    assert client.get(f"/api/segments/{seg['id']}/audio").status_code == 401
    # 비미디어 경로는 쿼리 토큰을 받지 않는다
    assert client.get(f"/api/projects?token={TOKEN}").status_code == 401
