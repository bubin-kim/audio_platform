"""품질 검사(기대 조각 수) + ntfy 알림 테스트 (V2-6 — docs/14)."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import app.hooks.ntfy as ntfy_module
from app.core.config import Settings
from app.hooks.events import on_processing_done, on_processing_failed
from app.hooks.ntfy import NtfyClient, register_ntfy_subscribers
from tests.conftest import upload_file


def _project_payload(expected: int | None = None) -> dict:
    p = {
        "name": "품질검사",
        "domain": None,
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [],
    }
    if expected is not None:
        p["expected_segments_per_source"] = expected
    return p


def _cut(client: TestClient, make_wav: Callable[..., Path], *, expected: int | None,
         duration: float = 3.0) -> dict:
    """프로젝트→업로드→커팅까지 돌리고 완료된 Job(dict)을 돌려준다."""
    pid = client.post("/api/projects", json=_project_payload(expected)).json()["id"]
    wav = make_wav(duration_sec=duration, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    jid = client.post(f"/api/datasets/{ds_id}/process").json()["id"]
    return client.get(f"/api/jobs/{jid}").json()


# --- 품질 검사 (Job.params.quality_check) ---


def test_quality_check_ok_when_count_matches(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    job = _cut(client, make_wav, expected=3, duration=3.0)  # 3초/1초 = 정확히 3
    qc = job["params"]["quality_check"]
    assert qc["ok"] is True
    assert qc["sources"][0]["status"] == "ok"
    assert qc["sources"][0]["actual"] == 3


def test_quality_check_shortfall(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """교수님 시나리오: 30개 기대인데 덜 나옴 → shortfall 기록."""
    job = _cut(client, make_wav, expected=5, duration=3.0)  # 3개만 나옴
    qc = job["params"]["quality_check"]
    assert qc["ok"] is False
    src = qc["sources"][0]
    assert src["status"] == "shortfall"
    assert (src["expected"], src["actual"]) == (5, 3)
    assert src["filename"] == "rec.wav"  # 어느 원본인지 특정 가능(재녹음 대상)


def test_quality_check_excess(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    job = _cut(client, make_wav, expected=2, duration=3.0)  # 3개 > 기대 2
    assert job["params"]["quality_check"]["sources"][0]["status"] == "excess"


def test_quality_check_skipped_when_unset(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """기대치 미설정 프로젝트는 검사 없음 — 기존 프로젝트 무영향 (P4)."""
    job = _cut(client, make_wav, expected=None)
    assert "quality_check" not in job["params"]


# --- ntfy 발송 ---


class _NtfyRecorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"id": "msg1"})


def _client_with(rec: _NtfyRecorder) -> NtfyClient:
    return NtfyClient(
        server="https://ntfy.sh", topic="test-topic", timeout_sec=5.0,
        transport=httpx.MockTransport(rec),
    )


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_register_noop_without_topic() -> None:
    assert register_ntfy_subscribers(_settings()) is False
    assert len(on_processing_done._subscribers) == 0


def test_register_with_topic() -> None:
    assert register_ntfy_subscribers(_settings(ntfy_topic="t1")) is True
    assert len(on_processing_done._subscribers) == 1
    assert len(on_processing_failed._subscribers) == 1


@pytest.fixture
def ntfy_env(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> _NtfyRecorder:
    """구독 등록 + 동기 실행 + 가짜 발송 클라이언트."""
    import app.background.worker as worker_module

    monkeypatch.setattr(ntfy_module, "_spawn", lambda target, **kw: target(**kw))
    monkeypatch.setattr(ntfy_module, "SessionLocal", worker_module.SessionLocal)
    rec = _NtfyRecorder()
    monkeypatch.setattr(ntfy_module, "_make_client", lambda: _client_with(rec))
    register_ntfy_subscribers(_settings(ntfy_topic="test-topic"))
    return rec


def test_done_notification_normal(
    client: TestClient, ntfy_env: _NtfyRecorder, make_wav: Callable[..., Path]
) -> None:
    _cut(client, make_wav, expected=3)  # 정확히 3 → 정상 알림
    assert len(ntfy_env.requests) == 1
    req = ntfy_env.requests[0]
    assert req.url.path == "/test-topic"
    body = req.content.decode("utf-8")
    assert "✅" in body and "3조각" in body
    assert req.headers.get("Priority", "default") == "default"


def test_done_notification_quality_warning(
    client: TestClient, ntfy_env: _NtfyRecorder, make_wav: Callable[..., Path]
) -> None:
    """조각 부족 → 경고 우선순위(high) + 부족 내용 포함 (교수님 요구 핵심)."""
    _cut(client, make_wav, expected=5)  # 3/5 부족
    req = ntfy_env.requests[-1]
    body = req.content.decode("utf-8")
    assert "재녹음" in body
    assert "3/5조각" in body and "부족" in body
    assert "rec.wav" in body  # 어느 원본인지
    assert req.headers["Priority"] == "high"


def test_failed_notification(
    client: TestClient, ntfy_env: _NtfyRecorder, make_wav: Callable[..., Path]
) -> None:
    """커팅 실패 → ❌ 알림 (파일명 충돌로 실패 유발)."""
    from datetime import date as _date

    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    today = _date.today().strftime("%Y%m%d")
    client._storage.save(f"segments/{ds_id}/{today}_001.wav", b"collision")

    client.post(f"/api/datasets/{ds_id}/process")
    req = ntfy_env.requests[-1]
    body = req.content.decode("utf-8")
    assert "❌" in body and "파일명 충돌" in body
    assert req.headers["Priority"] == "high"


def test_ntfy_failure_does_not_break_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_wav: Callable[..., Path]
) -> None:
    """ntfy 서버 다운이어도 커팅 Job은 정상 완료 (P4)."""
    import app.background.worker as worker_module

    monkeypatch.setattr(ntfy_module, "_spawn", lambda target, **kw: target(**kw))
    monkeypatch.setattr(ntfy_module, "SessionLocal", worker_module.SessionLocal)
    monkeypatch.setattr(
        ntfy_module, "_make_client",
        lambda: NtfyClient(
            server="https://ntfy.sh", topic="t", timeout_sec=1.0,
            transport=httpx.MockTransport(lambda r: httpx.Response(500)),
        ),
    )
    register_ntfy_subscribers(_settings(ntfy_topic="t"))
    job = _cut(client, make_wav, expected=3)
    assert job["status"] == "done"  # 알림 실패와 무관하게 Job 성공
