"""event_detection 커팅 전략 테스트 (V2-9 — docs/17).

합성 신호로 검증한다: 알려진 위치에 톤 버스트를 심고 그 위치를 찾는지 본다.
실파일 골든 케이스는 사람이 검수한 정답으로 별도 확인했다(docs/17 §2c).
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.audio.cutting import get_strategy
from app.audio.cutting.event_detection import EventDetectionStrategy

SR = 16000
BAND = {"band_low_hz": 1800, "band_high_hz": 2200}


def _make_file(tmp_path: Path, event_times: list[float], duration: float = 30.0,
               noise_db: float = -40.0, tone_hz: float = 2000.0,
               tone_amp: float = 0.25, name: str = "synth.wav") -> Path:
    """배경 잡음 + 지정 위치의 톤 버스트(0.5초)로 합성 파일을 만든다."""
    rng = np.random.default_rng(42)
    n = int(duration * SR)
    y = rng.normal(0, 10 ** (noise_db / 20), n).astype(np.float32)
    for t in event_times:
        a = int(t * SR)
        b = min(n, a + int(0.5 * SR))
        tt = np.arange(b - a) / SR
        env = np.hanning(b - a)  # 부드러운 시작·끝 (실제 경적과 비슷)
        y[a:b] += (tone_amp * np.sin(2 * np.pi * tone_hz * tt) * env).astype(np.float32)
    path = tmp_path / name
    sf.write(path, y, SR, subtype="PCM_16")
    return path


def test_registered_in_registry() -> None:
    """registry에 등록돼 Project.cutting_mode로 선택 가능해야 한다 (P1)."""
    assert isinstance(get_strategy("event_detection"), EventDetectionStrategy)


def test_detects_known_event_positions(tmp_path: Path) -> None:
    truth = [3.0, 9.0, 15.0, 21.0, 27.0]
    wav = _make_file(tmp_path, truth)
    strategy = EventDetectionStrategy()
    events = strategy.detect_events(wav, {"segment_sec": 4.0, **BAND})

    matched = [t for t in truth if any(abs(t - e) <= 1.0 for e in events)]
    assert len(matched) == len(truth), f"검출 {events}, 정답 {truth}"


def test_cut_produces_fixed_length_segments(tmp_path: Path) -> None:
    """조각 길이는 segment_sec로 균일해야 한다 (학습 데이터셋 요건)."""
    wav = _make_file(tmp_path, [5.0, 12.0, 19.0])
    strategy = EventDetectionStrategy()
    segments = list(
        strategy.cut(wav, {"segment_sec": 4.0, "pre_pad_sec": 1.5, **BAND})
    )
    assert len(segments) == 3
    for seg in segments:
        assert abs(seg.duration_sec - 4.0) < 0.01
        assert seg.start_sec >= 0.0


def test_pre_pad_places_event_inside_segment(tmp_path: Path) -> None:
    """이벤트가 조각 안에 들어와야 한다 — 앞 여유(pre_pad) 계약."""
    wav = _make_file(tmp_path, [10.0])
    strategy = EventDetectionStrategy()
    seg = next(iter(strategy.cut(wav, {"segment_sec": 5.0, "pre_pad_sec": 2.0, **BAND})))
    assert seg.start_sec <= 10.0 <= seg.end_sec
    assert abs(seg.start_sec - 8.0) < 1.0  # 이벤트 2초 전 부근에서 시작


def test_last_event_near_end_keeps_length(tmp_path: Path) -> None:
    """파일 끝에 걸친 이벤트도 고정 길이를 유지한다(뒤로 당김)."""
    wav = _make_file(tmp_path, [29.0], duration=30.0)
    strategy = EventDetectionStrategy()
    segments = list(strategy.cut(wav, {"segment_sec": 4.0, "pre_pad_sec": 2.0, **BAND}))
    assert segments, "끝부분 이벤트가 검출되지 않았다"
    for seg in segments:
        assert abs(seg.duration_sec - 4.0) < 0.01
        assert seg.end_sec <= 30.0 + 1e-6


def test_band_filter_ignores_out_of_band_events(tmp_path: Path) -> None:
    """대역 밖 소리는 무시한다 — 환경음에 묻힌 이벤트를 고르는 핵심 동작."""
    # 500Hz 버스트만 있는 파일을 1800~2200Hz 대역으로 검출 → 잡히면 안 된다
    wav = _make_file(tmp_path, [5.0, 12.0], tone_hz=500.0, name="lowtone.wav")
    strategy = EventDetectionStrategy()
    events = strategy.detect_events(wav, {"segment_sec": 4.0, **BAND})
    assert len(events) == 0, f"대역 밖 소리를 잡았다: {events}"


def test_validate_params() -> None:
    strategy = EventDetectionStrategy()
    with pytest.raises(ValueError, match="segment_sec"):
        strategy.validate_params({})
    with pytest.raises(ValueError, match="segment_sec"):
        strategy.validate_params({"segment_sec": 0})
    with pytest.raises(ValueError, match="함께 지정"):
        strategy.validate_params({"segment_sec": 5.0, "band_low_hz": 300})
    with pytest.raises(ValueError, match="작아야"):
        strategy.validate_params(
            {"segment_sec": 5.0, "band_low_hz": 2000, "band_high_hz": 1000}
        )


def test_empty_file_yields_nothing(tmp_path: Path) -> None:
    path = tmp_path / "empty.wav"
    sf.write(path, np.zeros(0, dtype=np.float32), SR, subtype="PCM_16")
    strategy = EventDetectionStrategy()
    assert list(strategy.cut(path, {"segment_sec": 4.0})) == []


# --- 프로젝트 생성 시점 파라미터 검증 (fail-fast) ---


def test_project_create_rejects_missing_required_param(client) -> None:
    """필수 파라미터가 없으면 프로젝트 생성에서 400 — 커팅 때까지 미루지 않는다.

    이전에는 생성이 통과하고 업로드까지 마친 뒤 커팅 Job에서야 실패했다.
    """
    r = client.post(
        "/api/projects",
        json={
            "name": "누락 검증",
            "domain": None,
            "cutting_mode": "event_detection",
            "cutting_params": {},  # segment_sec 없음
            "naming_pattern": "{date}_{seq:03d}",
            "label_schema": [],
        },
    )
    assert r.status_code == 400
    assert "segment_sec" in r.json()["detail"]


def test_project_create_rejects_half_specified_band(client) -> None:
    """대역은 하한·상한을 함께 줘야 한다."""
    r = client.post(
        "/api/projects",
        json={
            "name": "대역 검증",
            "domain": None,
            "cutting_mode": "event_detection",
            "cutting_params": {"segment_sec": 5.0, "band_low_hz": 1900},
            "naming_pattern": "{date}_{seq:03d}",
            "label_schema": [],
        },
    )
    assert r.status_code == 400


def test_project_create_accepts_valid_event_params(client) -> None:
    r = client.post(
        "/api/projects",
        json={
            "name": "정상 설정",
            "domain": None,
            "cutting_mode": "event_detection",
            "cutting_params": {
                "segment_sec": 5.0,
                "pre_pad_sec": 2.0,
                "band_low_hz": 1900,
                "band_high_hz": 2100,
            },
            "naming_pattern": "{date}_{seq:03d}",
            "label_schema": [],
        },
    )
    assert r.status_code == 201
