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

from statistics import median, pstdev
from typing import Any


def summarize_onsets(onsets: list[float], *, period_sec: float = 10.0) -> dict[str, Any]:
    """onset 리스트의 개수·오프셋 분포·간격을 요약한다.

    onsets는 오름차순이 아니어도 되며(정렬해서 처리), 빈 리스트도 허용한다
    (그 경우 통계 필드는 0/빈 리스트로 채운다).
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
        "offset_stddev_sec": round(pstdev(offsets), 3) if len(offsets) >= 2 else 0.0,
        "gaps_sec": gaps,
    }
