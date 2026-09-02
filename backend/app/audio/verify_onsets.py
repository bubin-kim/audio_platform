"""검출된 onset 목록의 자체 정합성 통계 (순수 로직, P2).

이 프로젝트의 녹음 사양(매 10초 구간, 초의 일의 자리가 5일 때 키를
눌렀음)을 이용해, 검출기가 실제로 맞았는지 **정답 없이도** 가늠할 수
있는 지표를 만든다 — 오프셋(`onset % 10`)이 전부 비슷한 값에 모이면
검출이 규칙적(=아마 맞음), 흩어지면 임계값·대역폭을 의심해야 한다는
신호다(docs/17 §2l의 "위상 규칙" 아이디어를 검출기 자체 진단용으로
재사용).

도메인 독립은 아니다 — "10초 간격"이라는 이 프로젝트 특유의 녹음
설계를 전제로 한다. 다른 도메인에서 재사용하려면 `period_sec`을
바꾸면 된다.
"""

import math
from statistics import median
from typing import Any


def _circular_stddev(offsets: list[float], period_sec: float) -> float:
    """오프셋의 **원형(circular) 표준편차** — 0초와 period_sec은 같은 위상이다.

    일반 표준편차를 쓰면 위상이 0초 근처인 파일에서 오프셋이 0.04와 9.99로
    갈려 표준편차가 4.6초까지 부풀려진다 — 실제로는 10초 간격으로 정확히
    잡고 있는데도 "위상 흔들림"으로 오판한다(실측 2026-08-28: 1일차 54개
    중 3개가 이 이유로 오판, 원형 표준편차로 바꾸니 0.24~0.34초로 정상).

    각 오프셋을 원 위의 각도로 보고 평균 벡터의 길이(R)로 산포를 잰다.
    R이 1에 가까우면 한 점에 모인 것(산포 0), 0에 가까우면 흩어진 것.
    """
    if len(offsets) < 2:
        return 0.0
    angles = [t / period_sec * 2 * math.pi for t in offsets]
    cos_mean = sum(math.cos(a) for a in angles) / len(angles)
    sin_mean = sum(math.sin(a) for a in angles) / len(angles)
    r = math.hypot(cos_mean, sin_mean)
    if r >= 1.0:
        return 0.0
    if r <= 0.0:
        return period_sec / 2  # 완전히 흩어짐 — 최대 산포
    return math.sqrt(-2 * math.log(r)) * period_sec / (2 * math.pi)


def summarize_onsets(onsets: list[float], *, period_sec: float = 10.0) -> dict[str, Any]:
    """onset 리스트의 개수·오프셋 분포·간격을 요약한다.

    onsets는 오름차순이 아니어도 되며(정렬해서 처리), 빈 리스트도 허용한다
    (그 경우 통계 필드는 0/빈 리스트로 채운다).

    `offset_stddev_sec`는 원형 표준편차다(§_circular_stddev) — 위상이 0초
    근처여도 올바르게 판정한다.
    """
    sorted_onsets = sorted(onsets)
    offsets = [round(t % period_sec, 3) for t in sorted_onsets]
    gaps = [
        round(b - a, 3) for a, b in zip(sorted_onsets, sorted_onsets[1:])
    ]

    return {
        "count": len(sorted_onsets),
        "onsets_sec": sorted_onsets,
        "offsets_sec": offsets,
        "offset_median_sec": round(median(offsets), 3) if offsets else None,
        "offset_stddev_sec": round(_circular_stddev(offsets, period_sec), 3),
        "gaps_sec": gaps,
    }
