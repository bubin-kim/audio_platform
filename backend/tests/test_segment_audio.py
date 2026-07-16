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


def test_audio_korean_filename_no_500(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """한글 파일명 세그먼트 재생 회귀 테스트 (실사고: 배포에서 500, 2026-07-15).

    HTTP 헤더는 latin-1만 허용 — 원시 한글 파일명을 Content-Disposition에 넣으면
    Response 생성이 UnicodeEncodeError로 죽는다. RFC 5987(filename*)로 실려야 한다.
    """
    from urllib.parse import quote

    payload = {
        "name": "한글파일명",
        "domain": None,
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{distance}_{seq:03d}",  # 한글 라벨이 파일명에 들어감
        "label_schema": [
            {"key": "distance", "type": "enum", "options": ["근거리", "원거리"], "required": True}
        ],
    }
    pid = client.post("/api/projects", json=payload).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    r = client.post(
        f"/api/datasets/{ds_id}/process",
        json={"common_labels": {"distance": "근거리"}},
    )
    assert r.status_code == 202, r.text
    seg = client.get(f"/api/datasets/{ds_id}/segments").json()["items"][0]
    assert "근거리" in seg["filename"]  # 전제: 한글 파일명

    r = client.get(f"/api/segments/{seg['id']}/audio")
    assert r.status_code == 200, r.text  # 사고 당시: 500 UnicodeEncodeError
    assert r.content[:4] == b"RIFF"
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("inline")
    assert f"filename*=UTF-8''{quote(seg['filename'])}" in disposition
