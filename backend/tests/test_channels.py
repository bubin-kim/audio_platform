"""다채널 → 모노 변환 규칙 테스트 (app/audio/channels.py).

핵심 계약: 채널마다 신호가 다르면 **가장 또렷한 채널**을 고른다.
단순 평균은 서로 다른 소리를 담은 채널들을 섞어 신호를 희석시킨다
(실측: 파일럿 4채널에서 평균 대비 +1.9~3.4dB 손해).
"""

import numpy as np

from app.audio.channels import to_mono

SR = 16000


def _noise(n: int, amp: float, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(0, amp, n).astype(np.float32)


def _tone_burst(n: int, sr: int, hz: float, amp: float, at_sec: float) -> np.ndarray:
    y = np.zeros(n, dtype=np.float32)
    a = int(at_sec * sr)
    b = min(n, a + int(0.5 * sr))
    t = np.arange(b - a) / sr
    y[a:b] = amp * np.sin(2 * np.pi * hz * t) * np.hanning(b - a)
    return y


def test_mono_input_passes_through() -> None:
    x = _noise(SR, 0.1)
    result = to_mono(x, SR)
    assert result.strategy == "single"
    assert result.samples.shape == x.shape


def test_single_channel_2d_passes_through() -> None:
    x = _noise(SR, 0.1).reshape(-1, 1)
    result = to_mono(x, SR)
    assert result.strategy == "single"
    assert result.samples.ndim == 1


def test_auto_picks_channel_with_clearest_signal() -> None:
    """이벤트가 뚜렷한 채널을 골라야 한다 — 평균은 이를 희석시킨다."""
    n = SR * 6
    quiet_bg = _noise(n, 0.02, seed=1)
    # ch0~2: 잡음만 / ch3: 잡음 + 톤 버스트 2개
    ch3 = _noise(n, 0.02, seed=4) + _tone_burst(n, SR, 2000, 0.35, 1.0)
    ch3 += _tone_burst(n, SR, 2000, 0.35, 4.0)
    data = np.stack([quiet_bg, _noise(n, 0.02, seed=2), _noise(n, 0.02, seed=3), ch3], axis=1)

    result = to_mono(data, SR, channel="auto", band=(1800, 2200))
    assert result.strategy == "auto"
    assert result.channel == 3, f"신호가 있는 채널을 못 골랐다 (고른 채널: {result.channel})"
    assert result.margin_db is not None and result.margin_db > 0


def test_auto_beats_mean_on_uncorrelated_channels() -> None:
    """상관 없는 채널들에서 auto가 mean보다 신호 여유가 크다 (실측 근거)."""
    from app.audio.channels import _band_margin_db

    n = SR * 6
    ch_signal = _noise(n, 0.02, seed=4) + _tone_burst(n, SR, 2000, 0.35, 2.0)
    data = np.stack(
        [_noise(n, 0.05, seed=i) for i in range(3)] + [ch_signal], axis=1
    )
    band = (1800, 2200)

    auto = to_mono(data, SR, channel="auto", band=band)
    mean = to_mono(data, SR, channel="mean")
    assert _band_margin_db(auto.samples, SR, band) > _band_margin_db(
        mean.samples, SR, band
    )


def test_explicit_channel_is_respected() -> None:
    n = SR * 3
    data = np.stack([_noise(n, 0.1, seed=i) for i in range(4)], axis=1)
    result = to_mono(data, SR, channel=2)
    assert result.strategy == "single"
    assert result.channel == 2
    assert np.allclose(result.samples, data[:, 2])


def test_out_of_range_channel_falls_back_to_auto() -> None:
    """녹음 장비가 바뀌어 채널 수가 줄어도 죽지 않는다."""
    n = SR * 3
    data = np.stack([_noise(n, 0.1, seed=i) for i in range(2)], axis=1)
    result = to_mono(data, SR, channel=99)
    assert result.strategy == "auto"
    assert result.channel in (0, 1)


def test_mean_strategy_available() -> None:
    n = SR * 3
    data = np.stack([_noise(n, 0.1, seed=i) for i in range(4)], axis=1)
    result = to_mono(data, SR, channel="mean")
    assert result.strategy == "mean"
    assert result.channel is None
    assert np.allclose(result.samples, data.mean(axis=1))


def test_band_out_of_nyquist_falls_back_to_broadband() -> None:
    """나이퀴스트를 넘는 대역 요청도 예외 없이 처리한다 (파일마다 sr이 다름)."""
    n = SR * 3
    data = np.stack([_noise(n, 0.1, seed=i) for i in range(2)], axis=1)
    result = to_mono(data, SR, channel="auto", band=(20000, 30000))
    assert result.samples.ndim == 1
    assert result.channel in (0, 1)
