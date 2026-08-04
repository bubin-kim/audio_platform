"""스펙트로그램 API + 원본 목록 테스트 (V2-8 — docs/16)."""

import base64
from collections.abc import Callable
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.audio.spectrogram import mel_spectrogram
from tests.conftest import upload_file


def _project(client: TestClient) -> int:
    return client.post(
        "/api/projects",
        json={
            "name": "스펙트럼",
            "domain": None,
            "cutting_mode": "fixed_interval",
            "cutting_params": {"interval_sec": 1.0},
            "naming_pattern": "{date}_{seq:03d}",
            "label_schema": [],
        },
    ).json()["id"]


# --- audio/ 순수 계산 ---


def test_mel_spectrogram_shape_and_range(make_wav: Callable[..., Path]) -> None:
    wav = make_wav(duration_sec=2.0, name="tone.wav")
    spec = mel_spectrogram(wav, max_cols=100)
    assert spec.n_mels == 96
    assert 0 < spec.cols <= 100
    raw = base64.b64decode(spec.data_b64)
    assert len(raw) == spec.n_mels * spec.cols
    arr = np.frombuffer(raw, dtype=np.uint8)
    assert arr.min() >= 0 and arr.max() <= 100  # 0~100 양자화 계약
    assert arr.max() > 0  # 톤이 있으니 전부 0(무음)일 수 없다


def test_display_range_adapts_to_content(make_wav: Callable[..., Path]) -> None:
    """표시 dB 범위는 파일 내용에 맞춰 잡힌다 (docs/16 — 대비 확보).

    고정 -80~0을 쓰면 분포가 좁은 녹음에서 대비가 죽어 묻힌 이벤트가 안 보인다.
    """
    wav = make_wav(duration_sec=2.0, name="tone.wav")
    spec = mel_spectrogram(wav, max_cols=100)
    assert spec.db_ceil > spec.db_floor
    assert spec.db_ceil - spec.db_floor >= 30.0  # MIN_DB_SPAN 보장
    # 범위를 실제로 활용해야 대비가 산다 — 밝은 쪽 값이 나와야 한다
    arr = np.frombuffer(base64.b64decode(spec.data_b64), dtype=np.uint8)
    assert arr.max() >= 90


def test_mel_spectrogram_long_file_caps_cols(make_wav: Callable[..., Path]) -> None:
    """긴 파일도 열 상한을 넘지 않는다 (docs/16 §2)."""
    wav = make_wav(duration_sec=30.0, name="long.wav")
    spec = mel_spectrogram(wav, max_cols=50)
    assert spec.cols <= 50
    assert abs(spec.duration_sec - 30.0) < 0.1


# --- API ---


def test_source_list_and_spectrogram(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = _project(client)
    wav = make_wav(duration_sec=3.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]

    # 원본 목록 (docs/16 신설)
    r = client.get(f"/api/datasets/{ds_id}/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["filename"] == "rec.wav"

    # 원본 스펙트로그램
    sid = body["items"][0]["id"]
    r = client.get(f"/api/source-files/{sid}/spectrogram")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, max-age=3600"
    spec = r.json()
    assert spec["n_mels"] == 96
    assert len(base64.b64decode(spec["data"])) == spec["n_mels"] * spec["cols"]


def test_segment_spectrogram(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = _project(client)
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    client.post(f"/api/datasets/{ds_id}/process")
    seg = client.get(f"/api/datasets/{ds_id}/segments").json()["items"][0]

    r = client.get(f"/api/segments/{seg['id']}/spectrogram")
    assert r.status_code == 200
    spec = r.json()
    assert spec["cols"] <= 240  # 세그먼트 상한 (docs/16 §2)
    assert abs(spec["duration_sec"] - 1.0) < 0.05  # 1초 간격 커팅


def test_spectrogram_404(client: TestClient) -> None:
    assert client.get("/api/source-files/9999/spectrogram").status_code == 404
    assert client.get("/api/segments/9999/spectrogram").status_code == 404
    assert client.get("/api/datasets/9999/sources").status_code == 404
