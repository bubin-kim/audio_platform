"""파형 피크 추출 — 세그먼트 미니 파형 렌더링용 (순수 오디오 로직, P2).

오디오를 bins개 구간으로 나눠 구간별 |진폭| 최대값을 돌려준다.
값은 풀스케일(1.0) 기준 절대값 — **세그먼트별 정규화를 하지 않는다**.
그래야 세그먼트끼리 파형 높이를 비교해 "비슷하게 잘렸는지"를 눈으로 확인할 수 있다.
"""

from pathlib import Path

import numpy as np
import soundfile as sf

from app.audio.channels import to_mono
from scipy import ndimage, signal as sig


def waveform_peaks(path: Path, bins: int = 60) -> list[float]:
    """구간별 절대 피크(0.0~1.0) bins개. 오디오가 bins보다 짧으면 실제 길이만큼.

    다채널은 가장 또렷한 채널을 고른다(app/audio/channels.py). float 서브타입 등으로 1.0을 넘는 샘플은
    렌더링 안정성을 위해 1.0으로 클램프한다.
    """
    if bins <= 0:
        raise ValueError(f"bins는 양수여야 합니다. 받은 값: {bins!r}")

    samples, _sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = np.abs(to_mono(samples, _sr).samples)  # (frames,)
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


def event_score_curve(
    path: Path,
    *,
    bins: int = 1200,
    band_low_hz: float | None = None,
    band_high_hz: float | None = None,
    bg_sec: float = 10.0,
) -> list[float]:
    """이벤트 탐색용 곡선 — 대역 통과 + 국소 배경 차감 후 0~1 정규화.

    전대역 진폭(waveform_peaks)은 환경음이 큰 녹음에서 묻힌 이벤트를 못 보여준다
    (실측 2026-08-08: 004에서 정답 5개 중 0개 일치). 대역을 좁히고 그 대역의
    '평소 수준'을 빼면 간헐적 이벤트만 남는다.

    band가 없으면 전대역을 그대로 쓴다 — 이때는 waveform_peaks와 성격이 같다.
    """
    samples, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = to_mono(samples, sr).samples
    if mono.size == 0:
        return []

    if band_low_hz and band_high_hz:
        nyq = sr / 2
        lo = max(1.0, min(band_low_hz, nyq - 1))
        hi = max(lo + 1.0, min(band_high_hz, nyq - 1))
        mono = sig.sosfilt(
            sig.butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos"), mono
        )

    n = mono.shape[0]
    effective = min(bins, n)
    edges = np.linspace(0, n, effective + 1, dtype=np.int64)
    rms = np.array([
        np.sqrt(np.mean(mono[edges[i]:edges[i + 1]] ** 2)) for i in range(effective)
    ])
    db = 20 * np.log10(np.maximum(rms, 1e-12))

    # 국소 배경(이동 중앙값)을 빼 '평소 대비 상승분'만 남긴다
    dt = (n / sr) / effective
    w = max(3, int(bg_sec / dt) | 1)
    rise = db - ndimage.median_filter(db, size=w, mode="nearest")

    # 0~1 정규화 (음수는 0) — 프론트가 파형과 같은 스케일로 그린다
    rise = np.maximum(rise, 0.0)
    peak = rise.max()
    if peak <= 0:
        return [0.0] * effective
    return [float(v) for v in (rise / peak)]
