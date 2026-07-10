"""세그먼트 오디오 스트림 테스트 — GET /segments/{id}/audio.

커팅으로 만들어진 wav 조각을 브라우저 <audio>가 재생할 수 있는 형태
(200 + audio/wav + inline)로 내려주는지 확인한다.
"""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import upload_file


def _make_segment(client: TestClient, make_wav: Callable[..., Path]) -> dict:
    """프로젝트 생성→업로드→커팅까지 돌리고 세그먼트 하나를 돌려준다."""
    payload = {
        "name": "심음",
        "domain": "heart",
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [],
    }
    pid = client.post("/api/projects", json=payload).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    r = client.post(f"/api/datasets/{ds_id}/process", json={})
    assert r.status_code == 202, r.text
    return client.get(f"/api/datasets/{ds_id}/segments").json()["items"][0]


def test_audio_streams_wav_inline(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    seg = _make_segment(client, make_wav)
    r = client.get(f"/api/segments/{seg['id']}/audio")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.headers["content-disposition"].startswith("inline")
    assert seg["filename"] in r.headers["content-disposition"]
    assert r.content[:4] == b"RIFF"  # 유효한 wav 헤더
    assert len(r.content) == seg["file_size"]


def test_audio_missing_segment_404(client: TestClient) -> None:
    r = client.get("/api/segments/99999/audio")
    assert r.status_code == 404
