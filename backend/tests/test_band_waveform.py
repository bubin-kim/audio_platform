"""band_waveform 테스트 — 대역통과 파형(표시 전용, docs/16 §7 추가8).

핵심 계약:
  ① 비프 대역 신호만 반영한다 (저역 소음에 반응하지 않는다)
  ② 자기 최대값으로 정규화해 약한 녹음에서도 형태가 보인다
  ③ 원래 레벨(peak_abs)을 잃지 않는다
  ④ 기존 전대역 파형(waveform_peaks)과 별개로 동작한다
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from app.audio.band_waveform import band_waveform_peaks
from app.audio.waveform import waveform_peaks

SR = 48000
ONSETS = [2.0, 5.0, 8.0]


def _make_file(tmp_path: Path, *, tone_amp: float = 0.3, name: str = "bw.wav") -> Path:
    """강한 저역 소음 + 2000Hz 짧은 톤 3개."""
    rng = np.random.default_rng(7)
    n = int(10.0 * SR)
    t = np.arange(n) / SR
    sos = signal.butter(4, 400, btype="lowpass", fs=SR, output="sos")
    y = signal.sosfilt(sos, rng.normal(0, 1.0, n)) * 0.5  # 저역이 지배
    for onset in ONSETS:
        m = (t >= onset) & (t < onset + 0.15)
        y[m] += tone_amp * np.sin(2 * np.pi * 2000 * t[m])
    y = (y / np.max(np.abs(y)) * 0.9).astype(np.float32)
    path = tmp_path / name
    sf.write(str(path), y, SR, subtype="PCM_16")
    return path


def test_peaks_align_with_tones(tmp_path: Path) -> None:
    """대역통과 파형의 최대 지점이 심어둔 톤 위치와 맞는다."""
    wav = _make_file(tmp_path)
    duration, peaks, _ = band_waveform_peaks(wav, bins=1000)
    assert duration == pytest.approx(10.0, abs=0.05)

    arr = np.array(peaks)
    # 상위 칸들이 톤 구간에 몰려야 한다
    top = np.argsort(arr)[-30:]
    top_sec = top / len(arr) * duration
    for sec in top_sec:
        assert any(abs(sec - o) < 0.4 for o in ONSETS), f"{sec:.2f}초는 톤 위치가 아님"


def test_normalized_to_unit_range(tmp_path: Path) -> None:
    """정규화되어 최대가 1.0 — 낮은 레벨 녹음도 화면에 보인다."""
    wav = _make_file(tmp_path)
    _, peaks, peak_abs = band_waveform_peaks(wav, bins=500)
    assert max(peaks) == pytest.approx(1.0, abs=1e-3)
    assert min(peaks) >= 0.0
    assert peak_abs > 0


def test_quiet_file_still_visible(tmp_path: Path) -> None:
    """아주 작은 녹음(-60dBFS급)도 정규화 덕에 형태가 남는다.

    전대역 절대 파형은 같은 파일에서 거의 0으로 뭉개진다 —
    이 테스트가 신규 경로의 존재 이유다(실측 근거는 모듈 docstring).
    """
    wav = _make_file(tmp_path, tone_amp=0.3, name="quiet.wav")
    y, sr = sf.read(str(wav), dtype="float32")
    quiet = tmp_path / "very_quiet.wav"
    sf.write(str(quiet), (y * 0.001).astype(np.float32), sr, subtype="PCM_24")

    _, band_peaks, peak_abs = band_waveform_peaks(quiet, bins=500)
    plain = waveform_peaks(quiet, bins=500)

    assert max(band_peaks) == pytest.approx(1.0, abs=1e-3)  # 보인다
    assert max(plain) < 0.01  # 기존 파형은 사실상 안 보인다
    assert peak_abs < 0.01  # 원래 레벨은 보존


def test_band_ignores_low_frequency_noise(tmp_path: Path) -> None:
    """대역 밖(저역)만 있는 파일은 뚜렷한 봉우리가 생기지 않는다."""
    rng = np.random.default_rng(3)
    n = int(5.0 * SR)
    sos = signal.butter(4, 300, btype="lowpass", fs=SR, output="sos")
    y = (signal.sosfilt(sos, rng.normal(0, 1.0, n)) * 0.5).astype(np.float32)
    path = tmp_path / "lowonly.wav"
    sf.write(str(path), y, SR, subtype="PCM_16")

    _, peaks, _ = band_waveform_peaks(path, bins=400)
    arr = np.array(peaks)
    # 톤이 있을 때처럼 소수 칸에 에너지가 몰리지 않는다
    assert float(np.median(arr)) > 0.05, "저역 잡음은 고르게 퍼져야 한다"


def test_bins_respected(tmp_path: Path) -> None:
    wav = _make_file(tmp_path)
    _, peaks, _ = band_waveform_peaks(wav, bins=321)
    assert len(peaks) == 321


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"band_low_hz": 0}, "band_low_hz"),
        ({"band_low_hz": 2500, "band_high_hz": 2000}, "band_low_hz"),
        ({"bins": 0}, "bins"),
    ],
)
def test_validates_params(tmp_path: Path, kwargs: dict, message: str) -> None:
    wav = _make_file(tmp_path)
    with pytest.raises(ValueError, match=message):
        band_waveform_peaks(wav, **kwargs)
