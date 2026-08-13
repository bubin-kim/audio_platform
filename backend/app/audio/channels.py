"""다채널 오디오를 분석용 모노 신호로 만드는 규칙 (순수 로직, P2).

**기본은 채널 평균(mean)이다** — 사용자 청취 GT로 검증된 결과다
(2026-08-13, 파일럿 004/005 4채널):

| 방식 | 004 Recall | 005 Recall |
|---|---|---|
| ch3 단독 | 35.5% | 68.6% |
| **평균(mean)** | **58.1%** | **80.0%** |

대역 에너지 여유(p99.5-p30)만 보면 특정 채널이 더 좋아 보이지만, 실제 정답
대비 성능은 평균이 크게 앞섰다. 채널마다 이벤트가 잡히는 정도가 달라
평균이 여러 마이크의 증거를 합치는 효과가 있는 것으로 보인다.
**추정 지표보다 정답 기반 측정을 따른다.**

"auto"(여유 최대 채널)와 명시 지정도 지원하지만, 근거가 있을 때만 쓴다.

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
    channel: int | str | None = "mean",
    band: tuple[float, float] | None = None,
) -> ChannelChoice:
    """(frames, channels) → 분석용 모노 1차원 신호.

    channel:
      - "mean"(기본): 전 채널 평균. GT 검증에서 가장 성능이 좋았다.
      - "auto": 신호 여유가 가장 큰 채널을 고른다 (대역 지정 시 그 대역 기준).
      - int: 그 채널을 그대로 쓴다 (범위를 벗어나면 auto로 폴백).
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
