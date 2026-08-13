"""다채널 오디오를 분석용 모노 신호로 만드는 규칙 (순수 로직, P2).

**왜 단순 평균이 아닌가** (실측 2026-08-13, 파일럿 004/005 — 둘 다 4채널):
채널 간 상관이 매우 낮았다(ch0 기준 ch3는 -0.004·-0.215). 마이크 위치·지향성이
달라 서로 다른 소리를 담고 있다는 뜻이다. 이때 단순 평균은 신호를 희석시킨다 —
검출 대역(1900–2100Hz)에서 배경 대비 여유가 평균 9.1/25.0dB인데,
가장 좋은 채널 하나만 쓰면 11.0/28.4dB로 **+1.9~3.4dB 개선**된다.

그래서 기본은 "가장 또렷한 채널 자동 선택"이다. 어느 채널을 골랐는지는
호출부가 기록·표시할 수 있도록 함께 돌려준다.

도메인 독립(P1): 여기에는 경적·심음 같은 도메인 값이 없다. 판정은 들어온
신호의 통계로만 한다. 대역을 주면 그 대역 기준으로, 안 주면 전대역으로 고른다.
"""

from dataclasses import dataclass

import numpy as np
from scipy import signal as sig


@dataclass
class ChannelChoice:
    """모노화 결과 + 근거 (재현성·표시용)."""

    samples: np.ndarray  # (frames,) 모노 신호
    strategy: str  # "single" | "auto" | "mean"
    channel: int | None  # 선택된 채널 (mean이면 None)
    margin_db: float | None  # 선택 근거가 된 신호 여유 (auto일 때만)


def _band_margin_db(
    x: np.ndarray,
    sr: int,
    band: tuple[float, float] | None,
    win_sec: float = 0.05,
) -> float:
    """신호 여유 = 상위 신호(p99.5) - 배경(p30), dB.

    간헐적 이벤트가 배경 위로 얼마나 솟는지를 재는 값이다. 클수록 검출에 유리.
    """
    y = x
    if band is not None:
        lo, hi = band
        nyq = sr / 2
        # 나이퀴스트를 넘는 대역 요청은 무시하고 전대역으로 (파일마다 sr이 다를 수 있음)
        if 0 < lo < hi < nyq:
            y = sig.sosfilt(
                sig.butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos"), x
            )

    win = max(1, int(sr * win_sec))
    n = len(y) // win
    if n < 2:
        return 0.0
    frames = y[: n * win].reshape(n, win)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-12))
    return float(np.percentile(db, 99.5) - np.percentile(db, 30))


def to_mono(
    samples: np.ndarray,
    sr: int,
    *,
    channel: int | str | None = "auto",
    band: tuple[float, float] | None = None,
) -> ChannelChoice:
    """(frames, channels) → 분석용 모노 1차원 신호.

    channel:
      - "auto"(기본): 신호 여유가 가장 큰 채널을 고른다.
      - int: 그 채널을 그대로 쓴다 (범위를 벗어나면 auto로 폴백).
      - "mean": 전 채널 평균 (기존 동작 — 채널이 같은 소리를 담을 때 잡음이 준다).
    band: 여유를 잴 주파수 대역. None이면 전대역.
    """
    if samples.ndim == 1:
        return ChannelChoice(samples, "single", 0, None)

    n_ch = samples.shape[1]
    if n_ch == 1:
        return ChannelChoice(samples[:, 0], "single", 0, None)

    if channel == "mean":
        return ChannelChoice(samples.mean(axis=1), "mean", None, None)

    if isinstance(channel, int):
        if 0 <= channel < n_ch:
            margin = _band_margin_db(samples[:, channel], sr, band)
            return ChannelChoice(samples[:, channel], "single", channel, margin)
        # 잘못된 채널 번호는 조용히 무시하고 자동 선택으로 (녹음 장비가 바뀔 수 있음)

    margins = [_band_margin_db(samples[:, c], sr, band) for c in range(n_ch)]
    best = int(np.argmax(margins))
    return ChannelChoice(samples[:, best], "auto", best, margins[best])
