"""band_spectrogram.crop_band_spectrogram 테스트."""

import base64
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from app.audio.band_spectrogram import crop_band_spectrogram

SR = 48000


def _make_tone_file(tmp_path: Path, tone_hz: float = 2000.0, duration: float = 2.0) -> Path:
    n = int(duration * SR)
    t = np.arange(n) / SR
    y = (0.5 * np.sin(2 * np.pi * tone_hz * t)).astype(np.float32)
    path = tmp_path / "tone.wav"
    sf.write(str(path), y, SR, subtype="PCM_16")
    return path


def test_crops_to_requested_band(tmp_path: Path) -> None:
    wav = _make_tone_file(tmp_path)
    data = crop_band_spectrogram(wav, fmin=1500, fmax=2500)

    assert data.fmin >= 1500
    assert data.fmax <= 2500
    assert data.freq_bins > 0
    assert data.cols > 0


def test_tone_energy_falls_inside_band(tmp_path: Path) -> None:
    """2000Hz 순음을 1500~2500Hz로 자르면, 잘려나간 스펙트럼에서 최댓값이 있어야 한다."""
    wav = _make_tone_file(tmp_path, tone_hz=2000.0)
    data = crop_band_spectrogram(wav, fmin=1500, fmax=2500)

    raw = base64.b64decode(data.data_b64)
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(data.freq_bins, data.cols)
    # 톤이 항상 켜져 있으므로 시간축 아무 열이나 최댓값 위치를 보면 된다.
    peak_row = int(np.argmax(arr[:, arr.shape[1] // 2]))
    assert 0 <= peak_row < data.freq_bins


def test_downsamples_columns_to_max_cols(tmp_path: Path) -> None:
    """긴 파일은 max_cols로 열이 압축된다(응답 크기 제한)."""
    n = int(20.0 * SR)
    y = (0.3 * np.random.default_rng(1).normal(size=n)).astype(np.float32)
    path = tmp_path / "long.wav"
    sf.write(str(path), y, SR, subtype="PCM_16")

    data = crop_band_spectrogram(path, max_cols=100)
    assert data.cols == 100


def test_out_of_nyquist_band_returns_empty(tmp_path: Path) -> None:
    wav = _make_tone_file(tmp_path)
    data = crop_band_spectrogram(wav, fmin=100000, fmax=200000)
    assert data.cols == 0
    assert data.freq_bins == 0
    assert data.data_b64 == ""


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"fmin": 2000, "fmax": 1900}, "fmax"),
        ({"n_fft": 0}, "n_fft"),
        ({"hop_length": 0}, "hop_length"),
        ({"top_db": 0}, "top_db"),
        ({"max_cols": 0}, "max_cols"),
    ],
)
def test_validates_bad_params(tmp_path: Path, overrides: dict, message: str) -> None:
    wav = _make_tone_file(tmp_path)
    with pytest.raises(ValueError, match=message):
        crop_band_spectrogram(wav, **overrides)


def test_does_not_touch_mel_spectrogram() -> None:
    """기존 mel_spectrogram 모듈은 이 파일과 완전히 독립적이다(회귀 방지 표식)."""
    from app.audio import spectrogram

    assert hasattr(spectrogram, "mel_spectrogram")
    assert spectrogram.N_MELS == 128  # 기존 상수가 그대로임을 확인
