"""periodic_beep 커팅 전략 테스트.

핵심 계약:
  ① 주기적으로 반복되는 이벤트를 주기 수만큼 찾는다
  ② 잘라낸 조각은 **원본 샘플**이다 (탐지에만 가공 신호를 쓴다)
  ③ 조각마다 탐지 근거(시각·위상)를 남긴다
  ④ 임계값 방식이 놓치는 약한 신호도 잡는다
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from app.audio.cutting import get_strategy
from app.audio.cutting.periodic_beep import PeriodicBeepStrategy

SR = 48000
ONSETS = [5.0, 15.0, 25.0, 35.0, 45.0]


def _make_file(
    tmp_path: Path,
    duration: float = 50.0,
    noise_amp: float = 0.3,
    tone_amp: float = 0.3,
    name: str = "periodic.wav",
) -> Path:
    """저역 배경잡음 + 10초마다 2000Hz 짧은 톤."""
    rng = np.random.default_rng(11)
    n = int(duration * SR)
    t = np.arange(n) / SR
    sos = signal.butter(4, 500, btype="lowpass", fs=SR, output="sos")
    y = (signal.sosfilt(sos, rng.normal(0, 1.0, n)) * noise_amp).astype(np.float64)
    for onset in ONSETS:
        m = (t >= onset) & (t < onset + 0.2)
        y[m] += tone_amp * np.sin(2 * np.pi * 2000 * t[m])
    y = (y / np.max(np.abs(y))).astype(np.float32)
    path = tmp_path / name
    sf.write(str(path), y, SR, subtype="PCM_16")
    return path


def test_registered_in_registry() -> None:
    assert get_strategy("periodic_beep") is not None


def test_finds_all_periodic_events(tmp_path: Path) -> None:
    wav = _make_file(tmp_path)
    segments = list(PeriodicBeepStrategy().cut(wav, {"period_sec": 10.0}))
    assert len(segments) == len(ONSETS)
    for seg, expected in zip(segments, ONSETS):
        detected = seg.detection["detected_at_sec"]
        assert abs(detected - expected) < 0.5, f"{expected}초 근방 못 찾음: {detected}"


def test_phase_is_consistent(tmp_path: Path) -> None:
    """검출된 이벤트의 위상(주기 내 위치)이 일정해야 한다."""
    wav = _make_file(tmp_path)
    segments = list(PeriodicBeepStrategy().cut(wav, {"period_sec": 10.0}))
    phases = [s.detection["phase_sec"] for s in segments]
    assert float(np.std(phases)) < 0.5, phases


def test_segments_are_original_samples(tmp_path: Path) -> None:
    """잘린 조각은 원본 샘플 그대로 — 대역통과된 신호가 아니다."""
    wav = _make_file(tmp_path)
    original, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    segments = list(PeriodicBeepStrategy().cut(wav, {"period_sec": 10.0}))

    seg = segments[0]
    a = int(seg.start_sec * sr)
    expected = original[a : a + seg.samples.shape[0]]
    assert np.allclose(seg.samples, expected, atol=1e-6)


def test_before_after_window(tmp_path: Path) -> None:
    wav = _make_file(tmp_path)
    segments = list(
        PeriodicBeepStrategy().cut(wav, {"period_sec": 10.0, "before_sec": 2, "after_sec": 1})
    )
    interior = [s for s in segments if s.start_sec > 0.1 and s.end_sec < 49.9]
    assert interior
    for seg in interior:
        assert abs(seg.duration_sec - 3.0) < 0.2


def test_exact_count_on_weak_signal(tmp_path: Path) -> None:
    """약한 신호에서도 **정확히 주기 수만큼** 찾는다 — 오탐이 섞이지 않는다.

    임계값 방식(event_detection)은 같은 신호에서 개수가 흔들린다(오탐이
    섞이거나 미탐이 난다). 주기 방식은 주기 창마다 하나씩 고르므로 개수가
    보장되고, 위상 일관성으로 맞았는지 확인할 수 있다.
    """
    wav = _make_file(tmp_path, noise_amp=0.5, tone_amp=0.25, name="weak.wav")
    segments = list(PeriodicBeepStrategy().cut(wav, {"period_sec": 10.0}))

    assert len(segments) == len(ONSETS)
    for seg, expected in zip(segments, ONSETS):
        assert abs(seg.detection["detected_at_sec"] - expected) < 0.5
    phases = [s.detection["phase_sec"] for s in segments]
    assert float(np.std(phases)) < 0.5, phases


@pytest.mark.parametrize(
    "params,message",
    [
        ({"period_sec": 0}, "period_sec"),
        ({"period_sec": 10, "before_sec": -1}, "before_sec"),
        ({"period_sec": 10, "band_low_hz": 2500, "band_high_hz": 2000}, "band_low_hz"),
    ],
)
def test_validate_params(params: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PeriodicBeepStrategy().validate_params(params)
