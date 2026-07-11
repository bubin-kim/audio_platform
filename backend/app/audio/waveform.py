"""파형 피크 추출 — 세그먼트 미니 파형 렌더링용 (순수 오디오 로직, P2).

오디오를 bins개 구간으로 나눠 구간별 |진폭| 최대값을 돌려준다.
값은 풀스케일(1.0) 기준 절대값 — **세그먼트별 정규화를 하지 않는다**.
그래야 세그먼트끼리 파형 높이를 비교해 "비슷하게 잘렸는지"를 눈으로 확인할 수 있다.
"""

from pathlib import Path

import numpy as np
import soundfile as sf


def waveform_peaks(path: Path, bins: int = 60) -> list[float]:
    """구간별 절대 피크(0.0~1.0) bins개. 오디오가 bins보다 짧으면 실제 길이만큼.

    다채널은 채널 평균으로 모노화한다. float 서브타입 등으로 1.0을 넘는 샘플은
    렌더링 안정성을 위해 1.0으로 클램프한다.
    """
    if bins <= 0:
        raise ValueError(f"bins는 양수여야 합니다. 받은 값: {bins!r}")

    samples, _sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = np.abs(samples).mean(axis=1)  # (frames,)
    n = mono.shape[0]
    if n == 0:
        return []

    effective_bins = min(bins, n)
    # 구간 경계: 마지막 구간이 나머지를 모두 갖도록 등분
    edges = np.linspace(0, n, effective_bins + 1, dtype=np.int64)
    peaks = [
        float(np.clip(mono[edges[i] : edges[i + 1]].max(), 0.0, 1.0))
        for i in range(effective_bins)
    ]
    return peaks
