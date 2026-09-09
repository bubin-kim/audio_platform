"""detect_beep_offsets 테스트 — offset(소리가 끝나는 시각).

onset은 "소리가 시작하는 순간", offset은 "소리가 멈추는 순간"이다.
`verify_onsets`의 `offsets_sec`(=onset % period, 위상)와는 다른 개념이다.
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from app.audio.band_beep_detector import detect_beep_offsets, detect_beep_onsets
from app.audio.verify_onsets import summarize_onsets

SR = 48000
ONSETS = [5.0, 15.0, 25.0]


def _make(tmp_path: Path, dur: float, name: str = "beep.wav") -> Path:
    rng = np.random.default_rng(5)
    n = int(30 * SR)
    t = np.arange(n) / SR
    sos = signal.butter(4, 500, btype="lowpass", fs=SR, output="sos")
    y = signal.sosfilt(sos, rng.normal(0, 1, n)) * 0.3
    for o in ONSETS:
        m = (t >= o) & (t < o + dur)
        y[m] += 0.3 * np.sin(2 * np.pi * 2000 * t[m])
    y = (y / np.max(np.abs(y))).astype(np.float32)
    p = tmp_path / name
    sf.write(str(p), y, SR, subtype="PCM_16")
    return p


@pytest.mark.parametrize("dur", [0.10, 0.15, 0.30])
def test_duration_tracks_real_length(tmp_path: Path, dur: float) -> None:
    """측정 지속시간이 실제 톤 길이를 따라간다(스무딩 여유 포함)."""
    wav = _make(tmp_path, dur, f"d{int(dur*1000)}.wav")
    onsets = detect_beep_onsets(wav, {"period_sec": 10.0})
    offsets, starts = detect_beep_offsets(wav, onsets, {"period_sec": 10.0})
    s = summarize_onsets(onsets, offsets_end_sec=offsets, sound_starts_sec=starts)

    measured = s["duration_median_sec"]
    # 엔벨로프 스무딩(20ms)만큼 길게 나오는 것은 정상 — 큰 오차만 잡는다.
    assert dur <= measured <= dur + 0.05, f"{dur}s 톤인데 {measured}s로 측정됨"


def test_duration_is_stable_across_events(tmp_path: Path) -> None:
    """onset이 톤의 어디에 찍혔든 지속시간이 흔들리지 않는다.

    회귀 방지: 예전에는 `offset - onset`으로 계산해, onset이 톤 끝부분에
    찍힌 경우(심은 5.000~5.150 톤에서 onset 5.138) 18ms가 나왔다.
    소리의 실제 시작(starts) 기준으로 재야 세 이벤트가 같은 값이 된다.
    """
    wav = _make(tmp_path, 0.15, "stable.wav")
    onsets = detect_beep_onsets(wav, {"period_sec": 10.0})
    offsets, starts = detect_beep_offsets(wav, onsets, {"period_sec": 10.0})
    s = summarize_onsets(onsets, offsets_end_sec=offsets, sound_starts_sec=starts)

    durations = s["durations_sec"]
    assert len(durations) == len(ONSETS)
    assert max(durations) - min(durations) < 0.02, durations
    assert min(durations) > 0.05, f"18ms류 버그 재발: {durations}"


def test_offset_is_after_sound_start(tmp_path: Path) -> None:
    wav = _make(tmp_path, 0.15, "order.wav")
    onsets = detect_beep_onsets(wav, {"period_sec": 10.0})
    offsets, starts = detect_beep_offsets(wav, onsets, {"period_sec": 10.0})
    for st, off in zip(starts, offsets):
        assert off > st


def test_offset_never_precedes_onset(tmp_path: Path) -> None:
    """회귀 방지: offset이 onset보다 앞서면 안 된다.

    실사고 2026-09-02: 피크를 onset ±offset_max_sec(2초)에서 찾다가
    onset 앞의 무관한 큰 소리를 잡아, 58개 원본 중 34개에서 offset이
    onset보다 최대 1.96초 앞섰다(예: 온셋 95.72s → 오프셋 93.86s).
    """
    wav = _make(tmp_path, 0.15, "inv.wav")
    # onset 바로 앞(4.0초)에 훨씬 큰 소리를 심어 역전을 유도한다.
    y, sr = sf.read(str(wav), dtype="float32")
    t = np.arange(len(y)) / sr
    m = (t >= 4.0) & (t < 4.2)
    y[m] += 0.9 * np.sin(2 * np.pi * 2000 * t[m])
    y = (y / np.max(np.abs(y))).astype(np.float32)
    sf.write(str(wav), y, sr, subtype="PCM_16")

    onsets = detect_beep_onsets(wav, {"period_sec": 10.0})
    offsets, starts = detect_beep_offsets(wav, onsets, {"period_sec": 10.0})
    for on, off in zip(onsets, offsets):
        assert off >= on, f"역전 발생: 온셋 {on} → 오프셋 {off}"


def test_empty_onsets(tmp_path: Path) -> None:
    wav = _make(tmp_path, 0.15, "empty.wav")
    assert detect_beep_offsets(wav, [], {}) == []


def test_summarize_without_offsets_is_backward_compatible() -> None:
    """offset을 안 넘기면 기존 필드는 그대로, 신규 필드는 비어 있다."""
    s = summarize_onsets([5.0, 15.0], period_sec=10.0)
    assert s["onsets_sec"] == [5.0, 15.0]
    assert s["offsets_sec"] == [5.0, 5.0]  # 위상(onset % 10)
    assert s["offsets_end_sec"] == []
    assert s["durations_sec"] == []
    assert s["duration_median_sec"] is None
