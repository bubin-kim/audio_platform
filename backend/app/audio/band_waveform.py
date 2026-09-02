"""대역통과 파형 — 비프 대역만 남긴 엔벨로프를 파형 칸으로 (순수 로직, P2).

`audio/waveform.py`(전대역 절대 피크)를 **대체하지 않는다.** 기존 파형은
그대로 두고, 비프 대역 탭에서만 쓰는 표시 전용 신규 경로다.

**왜 필요한가** (실측 2026-09-01, `260818_001.WAV`):
  본수집 녹음 레벨이 매우 낮아(비프음 -63dBFS) 전대역 절대 스케일 파형은
  1200칸 중 **98.7%가 0.5px 미만**으로 뭉개진다(캔버스 height=120 기준
  최대 막대 1.14px). 화면에는 가운데 가로줄만 보인다.

  게다가 전대역 파형은 저역 소음(엔진·환기팬·매장 음악)이 지배해, 설령
  크게 그려도 비프음 위치와 무관한 모양이 된다 — 비프 대역 탭의
  스펙트로그램·검출 onset과 **서로 다른 것을 가리키는** 상태가 된다.

  그래서 이 모듈은 ① 검출기와 **같은 대역통과**를 적용하고 ② 엔벨로프를
  구한 뒤 ③ **자기 최대값으로 정규화**해 형태가 보이게 만든다. 위(파형)·
  아래(스펙트로그램)·▲(onset)가 전부 같은 대역을 가리키게 된다.

정규화 때문에 **파일 간 절대 크기 비교는 불가능하다** — 그 용도로는 기존
"실제 크기" 탭의 전대역 파형을 쓴다. 응답에 실제 최대 진폭(`peak_abs`)을
함께 실어 원래 레벨을 잃지 않게 한다.
"""

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal as sig

from app.audio.channels import to_mono

# 검출기(band_beep_detector)와 같은 기본 대역 — 두 화면이 어긋나지 않게.
DEFAULT_BAND_LOW_HZ = 1800.0
DEFAULT_BAND_HIGH_HZ = 2200.0


def band_waveform_peaks(
    path: Path,
    *,
    bins: int = 1200,
    band_low_hz: float = DEFAULT_BAND_LOW_HZ,
    band_high_hz: float = DEFAULT_BAND_HIGH_HZ,
    smooth_ms: float = 20.0,
) -> tuple[float, list[float], float]:
    """대역통과 엔벨로프를 `bins`칸으로 요약한다.

    Returns:
        (duration_sec, peaks, peak_abs)
        - peaks: 0~1로 정규화된 칸별 최대값 (자기 최대 기준)
        - peak_abs: 정규화 전 실제 최대 진폭 (원래 레벨 보존용)
    """
    if band_low_hz <= 0:
        raise ValueError(f"band_low_hz는 0보다 커야 합니다. 받은 값: {band_low_hz!r}")
    if band_low_hz >= band_high_hz:
        raise ValueError(
            f"band_low_hz({band_low_hz})는 band_high_hz({band_high_hz})보다 작아야 합니다."
        )
    if bins <= 0:
        raise ValueError(f"bins는 양수여야 합니다. 받은 값: {bins!r}")

    samples, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if samples.shape[0] == 0:
        return 0.0, [], 0.0

    duration_sec = samples.shape[0] / sr
    # 검출기(band_beep_detector)와 같은 모노화 — 두 화면이 어긋나지 않게.
    mono = to_mono(samples, sr, channel="mean").samples.astype(np.float64)

    # 나이퀴스트를 넘는 대역은 필터를 만들 수 없다 — 잘라서 방어한다.
    nyq = sr / 2.0
    high = min(band_high_hz, nyq * 0.99)
    if band_low_hz >= high:
        return duration_sec, [0.0] * bins, 0.0

    sos = sig.butter(
        4, [band_low_hz, high], btype="bandpass", fs=sr, output="sos"
    )
    filtered = sig.sosfiltfilt(sos, mono)
    envelope = np.abs(sig.hilbert(filtered))

    win = max(1, int(smooth_ms / 1000.0 * sr))
    if win > 1:
        envelope = np.convolve(envelope, np.ones(win) / win, mode="same")

    peak_abs = float(np.max(envelope)) if envelope.size else 0.0

    # 칸별 최대값 — 짧은 비프음이 평균으로 흐려지지 않게(band_spectrogram과 같은 이유).
    edges = np.linspace(0, len(envelope), bins + 1).astype(int)
    peaks = np.zeros(bins, dtype=np.float64)
    for i in range(bins):
        a, b = edges[i], edges[i + 1]
        if b > a:
            peaks[i] = envelope[a:b].max()

    if peak_abs > 0:
        peaks = peaks / peak_abs

    return duration_sec, [round(float(v), 5) for v in peaks], round(peak_abs, 8)
