"""앰비소닉 빔포밍 — 특정 방향으로 지향성을 만들어 그 방향 신호만 키운다 (순수 로직, P2).

Zoom H3-VR은 **AmbiX 1차 앰비소닉**으로 녹음한다(docs/18 §5). 4채널은 별개
마이크가 아니라 하나의 음장을 4가지 지향 성분으로 분해한 것이라, 후처리로
**임의 방향의 가상 마이크를 합성**할 수 있다.

**채널 순서 주의**: 헤더 실측값은 `zTRK1=W · zTRK2=Y · zTRK3=Z · zTRK4=X`로,
일반적인 AmbiX 표기(W·X·Y·Z)와 **다르다.** 이 모듈은 실측 순서를 따른다.

수식 (1차 앰비소닉 지향성 합성):
```
out = W*(a) + (1-a) * (X*cosθ*cosφ + Y*sinθ*cosφ + Z*sinφ)
```
- `a`가 1이면 무지향(W만), 0이면 완전 8자형(방향 성분만)
- a=0.5이면 **카디오이드**(심장형) — 앞쪽만 듣고 뒤쪽은 억제. 가장 실용적

**왜 필요한가**: 본수집 데이터는 타겟 대역 배경 소음이 검출을 좌우한다
(3일차 SNR 44dB→검출 99%, 4일차 12.7dB→30%, docs/18). 차량 방향으로 빔을
만들면 그 방향 신호는 유지하면서 다른 방향 소음을 줄일 수 있어, 소음에
묻힌 세그먼트를 일부 복구할 수 있다. 라벨에 각도·거리가 이미 있다.
"""

from typing import Literal

import numpy as np

# 헤더 실측 채널 순서 (docs/18 §5) — W·Y·Z·X
CH_W, CH_Y, CH_Z, CH_X = 0, 1, 2, 3

PatternName = Literal["omni", "cardioid", "supercardioid", "hypercardioid", "figure8"]

# 1차 지향성 패턴별 W 가중치(a). out = a*W + (1-a)*방향성분
PATTERNS: dict[str, float] = {
    "omni": 1.0,            # 무지향 — W만 (빔포밍 없음)
    "cardioid": 0.5,        # 심장형 — 뒤쪽 억제, 가장 무난
    "supercardioid": 0.37,  # 초지향 — 측면 억제 강함
    "hypercardioid": 0.25,  # 극지향 — 정면 집중 최대
    "figure8": 0.0,         # 8자형 — 앞뒤만, 측면 완전 억제
}


def beamform(
    samples: np.ndarray,
    azimuth_deg: float,
    *,
    elevation_deg: float = 0.0,
    pattern: PatternName = "cardioid",
) -> np.ndarray:
    """4채널 AmbiX 신호를 지정 방향의 단일 채널로 합성한다.

    Args:
        samples: (frames, 4) — 채널 순서 W·Y·Z·X (헤더 실측 순서)
        azimuth_deg: 수평 방향(도). 0=정면, 90=왼쪽, 180=뒤, 270=오른쪽
        elevation_deg: 상하 방향(도). 0=수평
        pattern: 지향 패턴. 기본 cardioid

    Returns:
        (frames,) 모노 신호
    """
    if samples.ndim != 2 or samples.shape[1] < 4:
        raise ValueError(
            f"4채널 (frames, 4) 배열이 필요합니다. 받은 형태: {samples.shape}"
        )
    if pattern not in PATTERNS:
        raise ValueError(f"알 수 없는 패턴 '{pattern}'. 가능: {sorted(PATTERNS)}")

    a = PATTERNS[pattern]
    theta = np.deg2rad(azimuth_deg)
    phi = np.deg2rad(elevation_deg)

    w = samples[:, CH_W].astype(np.float64)
    y = samples[:, CH_Y].astype(np.float64)
    z = samples[:, CH_Z].astype(np.float64)
    x = samples[:, CH_X].astype(np.float64)

    # AmbiX는 SN3D 정규화 — 방향 성분에 √2를 곱해야 W와 스케일이 맞는다.
    directional = np.sqrt(2.0) * (
        x * np.cos(theta) * np.cos(phi)
        + y * np.sin(theta) * np.cos(phi)
        + z * np.sin(phi)
    )
    return a * w + (1.0 - a) * directional


def label_angle_to_azimuth(angle_code: int, step_deg: float = 45.0) -> float:
    """라벨의 각도 코드(0~7)를 방위각(도)으로 변환한다.

    본수집 라벨은 8방향을 0~7로 기록했다(docs/05). 0번이 물리적으로 어느
    방향인지는 **기록되지 않았다**(docs/18 §6 미확인 사항) — 따라서 이
    변환은 "0번=정면" 가정이며, 실제 기준이 확인되면 오프셋을 더해야 한다.
    """
    return (angle_code % 8) * step_deg


def scan_best_azimuth(
    samples: np.ndarray,
    sr: int,
    *,
    band: tuple[float, float] = (1900.0, 2100.0),
    step_deg: float = 15.0,
    pattern: PatternName = "cardioid",
) -> tuple[float, float]:
    """방위각을 훑어 타겟 대역 에너지가 가장 큰 방향을 찾는다.

    라벨의 0° 기준이 불확실하므로, 라벨 각도를 쓰는 대신 **데이터에서 직접**
    최적 방향을 찾는 용도. (best_azimuth_deg, band_energy) 반환.
    """
    from scipy import signal as sig

    best = (0.0, -np.inf)
    for az in np.arange(0.0, 360.0, step_deg):
        mono = beamform(samples, float(az), pattern=pattern)
        freqs, power = sig.welch(mono, sr, nperseg=min(4096, len(mono)))
        mask = (freqs >= band[0]) & (freqs <= band[1])
        if not mask.any():
            continue
        energy = float(power[mask].max())
        if energy > best[1]:
            best = (float(az), energy)
    return best
