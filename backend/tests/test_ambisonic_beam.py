"""앰비소닉 빔포밍 테스트 (docs/18 §5).

핵심 계약:
  ① 지정 방향의 소리를 키우고 반대 방향을 억제한다
  ② 채널 순서는 헤더 실측값 W·Y·Z·X를 따른다
  ③ 방향 스캔이 실제 음원 방향을 찾아낸다
  ④ 빔을 끄면(기본값) 기존 동작과 동일하다 — 회귀 방지
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from app.audio.ambisonic_beam import (
    PATTERNS,
    beamform,
    label_angle_to_azimuth,
    scan_best_azimuth,
)
from app.audio.band_beep_detector import detect_beep_onsets

SR = 48000


def _encode(mono: np.ndarray, az_deg: float, el_deg: float = 0.0) -> np.ndarray:
    """모노 소스를 특정 방향의 AmbiX(W·Y·Z·X)로 인코딩 — 테스트용 역변환."""
    th, ph = np.deg2rad(az_deg), np.deg2rad(el_deg)
    w = mono / np.sqrt(2.0)  # SN3D
    x = mono * np.cos(th) * np.cos(ph)
    y = mono * np.sin(th) * np.cos(ph)
    z = mono * np.sin(ph)
    return np.stack([w, y, z, x], axis=1)  # 헤더 실측 순서


def _tone(dur: float = 1.0, freq: float = 2000.0) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * freq * t)


def test_beam_boosts_target_direction() -> None:
    """조준 방향의 소리가 반대 방향보다 크게 나온다."""
    src = _tone()
    front = _encode(src, 0.0)
    back = _encode(src, 180.0)

    f = np.abs(beamform(front, 0.0, pattern="cardioid")).max()
    b = np.abs(beamform(back, 0.0, pattern="cardioid")).max()
    assert f > b * 2, f"정면 {f:.3f} vs 후면 {b:.3f} — 억제가 부족하다"


def test_omni_pattern_is_direction_independent() -> None:
    """무지향 패턴은 방향에 무관하게 같은 크기를 낸다(W만 쓰므로)."""
    src = _tone()
    amps = [
        np.abs(beamform(_encode(src, az), 0.0, pattern="omni")).max()
        for az in (0, 90, 180, 270)
    ]
    assert max(amps) - min(amps) < 1e-9, amps


def test_scan_finds_source_direction() -> None:
    """방향 스캔이 실제 음원 방향을 찾는다."""
    src = _tone()
    for true_az in (0.0, 90.0, 180.0, 270.0):
        samples = _encode(src, true_az)
        found, _ = scan_best_azimuth(samples, SR, step_deg=15.0)
        # 원형 거리로 비교 (0°와 359°는 가깝다)
        diff = abs((found - true_az + 180) % 360 - 180)
        assert diff <= 30, f"실제 {true_az}° → 탐색 {found}° (오차 {diff}°)"


def test_channel_order_is_wyzx() -> None:
    """채널 순서가 W·Y·Z·X임을 고정한다 (헤더 실측, docs/18 §5).

    일반 AmbiX 표기(W·X·Y·Z)로 착각하면 좌우와 앞뒤가 뒤바뀐다.
    """
    src = _tone()
    # 좌측(90°) 음원은 Y(ch1)에 최대 진폭이 실려야 한다
    left = _encode(src, 90.0)
    amps = [np.abs(left[:, c]).max() for c in range(4)]
    assert int(np.argmax(amps[1:])) + 1 == 1, f"좌측 음원인데 Y가 최대가 아님: {amps}"

    # 정면(0°) 음원은 X(ch3)에 최대
    front = _encode(src, 0.0)
    amps = [np.abs(front[:, c]).max() for c in range(4)]
    assert int(np.argmax(amps[1:])) + 1 == 3, f"정면 음원인데 X가 최대가 아님: {amps}"


def test_all_patterns_run() -> None:
    src = _tone()
    samples = _encode(src, 0.0)
    for p in PATTERNS:
        out = beamform(samples, 0.0, pattern=p)
        assert out.shape == (samples.shape[0],)
        assert np.isfinite(out).all()


def test_label_angle_conversion() -> None:
    assert label_angle_to_azimuth(0) == 0.0
    assert label_angle_to_azimuth(2) == 90.0
    assert label_angle_to_azimuth(8) == 0.0  # 순환


@pytest.mark.parametrize(
    "samples,message",
    [
        (np.zeros((100, 2)), "4채널"),
        (np.zeros(100), "4채널"),
    ],
)
def test_rejects_non_ambisonic(samples: np.ndarray, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        beamform(samples, 0.0)


def test_unknown_pattern_rejected() -> None:
    with pytest.raises(ValueError, match="패턴"):
        beamform(np.zeros((100, 4)), 0.0, pattern="bogus")  # type: ignore[arg-type]


# --- 검출기 연동 ---


def _make_4ch_file(tmp_path: Path, az_deg: float = 0.0) -> Path:
    """10초 주기로 비프음이 울리는 4채널 파일."""
    rng = np.random.default_rng(3)
    n = int(30.0 * SR)
    t = np.arange(n) / SR
    beep = np.zeros(n)
    for s in (5.0, 15.0, 25.0):
        m = (t >= s) & (t < s + 0.18)
        beep[m] = np.sin(2 * np.pi * 2000 * t[m])
    target = _encode(beep * 0.3, az_deg)

    sos = signal.butter(4, 500, btype="lowpass", fs=SR, output="sos")
    noise_mono = signal.sosfilt(sos, rng.normal(0, 1, n)) * 0.3
    mixed = target + _encode(noise_mono, 180.0)
    mixed = (mixed / np.max(np.abs(mixed)) * 0.9).astype(np.float32)

    path = tmp_path / f"beam_{int(az_deg)}.wav"
    sf.write(str(path), mixed, SR, subtype="PCM_24")
    return path


def test_detector_default_unchanged(tmp_path: Path) -> None:
    """beam 미지정(기본값)이면 기존 4채널 평균 경로를 쓴다 — 회귀 방지."""
    wav = _make_4ch_file(tmp_path)
    a = detect_beep_onsets(wav, {"period_sec": 10.0})
    b = detect_beep_onsets(wav, {"period_sec": 10.0, "beam": None})
    assert a == b
    assert len(a) == 3


def test_detector_with_beam_runs(tmp_path: Path) -> None:
    """beam='auto'로도 정상 검출된다."""
    wav = _make_4ch_file(tmp_path)
    onsets = detect_beep_onsets(wav, {"period_sec": 10.0, "beam": "auto"})
    assert len(onsets) == 3
    for got, expected in zip(onsets, (5.0, 15.0, 25.0)):
        assert abs(got - expected) < 0.6, f"{expected}초 근방 못 찾음: {got}"


def test_detector_with_fixed_azimuth(tmp_path: Path) -> None:
    """방위각을 숫자로 직접 줄 수도 있다."""
    wav = _make_4ch_file(tmp_path)
    onsets = detect_beep_onsets(wav, {"period_sec": 10.0, "beam": 0.0})
    assert len(onsets) == 3


def test_invalid_beam_rejected(tmp_path: Path) -> None:
    wav = _make_4ch_file(tmp_path)
    with pytest.raises(ValueError, match="beam"):
        detect_beep_onsets(wav, {"period_sec": 10.0, "beam": "sideways"})
