"""metadata.py 테스트 — 자동 메타 추출."""

from collections.abc import Callable
from pathlib import Path

from app.audio.metadata import extract_metadata


def test_extract_wav_pcm16(make_wav: Callable[..., Path]) -> None:
    path = make_wav(duration_sec=2.0, sample_rate=16000, channels=1)
    meta = extract_metadata(path)
    assert abs(meta.duration_sec - 2.0) < 1e-6
    assert meta.sample_rate == 16000
    assert meta.channels == 1
    assert meta.bit_depth == 16  # PCM_16
    assert meta.format == "wav"
    assert meta.file_size > 0


def test_extract_stereo_24bit(make_wav: Callable[..., Path]) -> None:
    path = make_wav(duration_sec=1.0, sample_rate=44100, channels=2, subtype="PCM_24")
    meta = extract_metadata(path)
    assert meta.channels == 2
    assert meta.bit_depth == 24
    assert meta.sample_rate == 44100
