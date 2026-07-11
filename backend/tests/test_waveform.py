"""파형 피크 테스트 — audio/waveform.py 단위 + API 통합 (06_API.md §4.5)."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.audio.waveform import waveform_peaks
from tests.conftest import upload_file


# --- 단위: 순수 함수 (web·DB 없음) ---


def test_peaks_shape_and_range(make_wav: Callable[..., Path]) -> None:
    path = make_wav(duration_sec=2.0, sample_rate=8000)
    peaks = waveform_peaks(path, bins=60)
    assert len(peaks) == 60
    assert all(0.0 <= p <= 1.0 for p in peaks)
    # 0.2 진폭 사인파 → 구간 피크는 대략 0.2 부근 (풀스케일 절대값, 정규화 없음)
    assert 0.15 < max(peaks) < 0.25


def test_peaks_absolute_scale_comparable(tmp_path: Path) -> None:
    """정규화하지 않으므로 조용한 파일과 큰 파일의 피크 높이가 다르게 나온다."""
    sr = 8000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    quiet = tmp_path / "quiet.wav"
    loud = tmp_path / "loud.wav"
    sf.write(str(quiet), (0.05 * np.sin(2 * np.pi * 220 * t)).astype("float32"), sr)
    sf.write(str(loud), (0.8 * np.sin(2 * np.pi * 220 * t)).astype("float32"), sr)
    q = max(waveform_peaks(quiet, bins=20))
    l = max(waveform_peaks(loud, bins=20))
    assert q < 0.1 < 0.7 < l  # 높이 비교 가능


def test_peaks_shorter_than_bins(tmp_path: Path) -> None:
    """bins보다 짧은 오디오는 실제 프레임 수만큼만 반환."""
    sr = 8000
    path = tmp_path / "tiny.wav"
    sf.write(str(path), np.ones(10, dtype="float32") * 0.5, sr)
    peaks = waveform_peaks(path, bins=60)
    assert len(peaks) == 10


def test_peaks_invalid_bins(make_wav: Callable[..., Path]) -> None:
    with pytest.raises(ValueError):
        waveform_peaks(make_wav(duration_sec=0.5), bins=0)


# --- API 통합 ---


def _make_segment(client: TestClient, make_wav: Callable[..., Path]) -> int:
    payload = {
        "name": "파형", "domain": None, "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}", "label_schema": [],
    }
    pid = client.post("/api/projects", json=payload).json()["id"]
    ds_id = upload_file(client, pid, make_wav(duration_sec=2.0, name="w.wav"), "w.wav")[
        "dataset_id"
    ]
    client.post(f"/api/datasets/{ds_id}/process")
    return client.get(f"/api/datasets/{ds_id}/segments").json()["items"][0]["id"]


def test_waveform_endpoint(client: TestClient, make_wav: Callable[..., Path]) -> None:
    seg_id = _make_segment(client, make_wav)
    r = client.get(f"/api/segments/{seg_id}/waveform")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["segment_id"] == seg_id
    assert body["duration_sec"] == pytest.approx(1.0, abs=0.01)
    assert len(body["peaks"]) == 60
    assert r.headers["Cache-Control"] == "private, max-age=3600"


def test_waveform_missing_segment_404(client: TestClient) -> None:
    assert client.get("/api/segments/99999/waveform").status_code == 404
