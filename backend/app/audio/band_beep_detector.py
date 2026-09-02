"""BandBeepDetector — 대역통과 필터 기반 비프음 onset 검출 (순수 로직, P2).

`cutting/event_detection.py`(STFT 대역 최대값 + baseline diff)와 달리, 이
모듈은 **신호 자체를 대역통과 필터로 걸러낸 뒤** 엔벨로프의 지역 적응형
피크로 onset을 찾는다. 저역 소음(엔진·환기팬·음악)이 강한 녹음에서 전대역
기준 피크 검출(평균+Nσ)이 광대역 충격음(문 닫는 소리 등)만 잡고 좁은 톤인
비프음을 놓치는 문제를 좁은 대역만 보는 것으로 우회한다.

**전대역 검출기(파형 뷰의 기존 피크 후보)를 대체하지 않는다** — 표시 전용
새 기능으로, 이 결과는 커팅에 쓰이지 않는다.

알고리즘:
```
1. 채널 평균(mean) → 모노
2. 대역통과(butterworth 4차, [band_low_hz, band_high_hz], filtfilt 제로위상)
3. 엔벨로프 = |hilbert(필터 출력)|
4. 짧게 스무딩(이동평균, smooth_ms)
5. 지역 적응형 임계값: 각 지점 ±local_window_sec 구간의 median + k*MAD
6. 전역 하한 결합: max(지역임계값, 전역median + k_global*전역MAD)
   ← 파일 경계에서 지역 통계가 무너지는 것 방어 (실측 근거는 DEFAULTS 주석)
7. find_peaks(envelope, height=임계값(배열), distance=min_gap_sec)
8. 피크 위치를 초 단위(소수점 3자리)로 반환
```

도메인 값(대역·k·min_gap 등)은 전부 함수 인자 기본값으로만 둔다(P1) —
호출자가 Project 설정에서 오버라이드할 수 있다.
"""

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import ndimage, signal as sig

from app.audio.channels import to_mono

DEFAULTS: dict[str, Any] = {
    "band_low_hz": 1800.0,
    "band_high_hz": 2200.0,
    # k=5는 최초 사양이었으나 합성 신호 실측(저역 배경잡음 + 1900~2100Hz
    # 톤 10개)에서 오탐 25개(진짜 10개 중 전부 포함하되 배경 튐도 다수
    # 포함)로 부족했다. k=8부터 오탐이 파일 경계(filtfilt 트랜지언트)
    # 2개로 줄고 진짜 10개가 정확히 잡혔다 — 실측 기반으로 8 채택.
    "k": 8.0,
    # 전역 하한(global floor) — 지역 임계값만 쓰면 **파일 맨앞·맨끝에서
    # 오탐**이 난다. median_filter(mode="nearest")가 경계에서 가장자리
    # 값을 복제해 지역 MAD가 거의 0이 되고(실측: 파일 끝에서 0.0000007,
    # 진짜 onset 지점의 1/25) 임계값이 비정상적으로 낮아지기 때문이다.
    # k를 올려도 안 고쳐진다(경계 오탐은 지역 통계 자체가 무너진 것이라
    # 배수를 키워도 같이 낮아짐 — 오히려 진짜 신호를 놓쳤다, 실측).
    # 그래서 "파일 전체 기준으로도 이 정도는 넘어야 한다"는 절대 하한을
    # 함께 건다: max(지역임계값, 전역median + k_global*전역MAD).
    # k_global=8은 실측으로 정했다 — 합성 100초(onset 10개)에서 경계
    # 오탐 2개만 정확히 제거, 실제 NAS 세그먼트 3개에서도 진짜 1개씩만.
    "k_global": 8.0,
    "min_gap_sec": 2.0,
    "local_window_sec": 2.0,
    "smooth_ms": 20.0,
}


def _param(params: dict[str, Any], key: str) -> Any:
    value = params.get(key)
    return DEFAULTS[key] if value is None else value


def validate_params(params: dict[str, Any]) -> None:
    lo = float(_param(params, "band_low_hz"))
    hi = float(_param(params, "band_high_hz"))
    if lo < 0:
        raise ValueError(f"band_low_hz는 0 이상이어야 합니다. 받은 값: {lo!r}")
    if lo >= hi:
        raise ValueError(f"band_low_hz({lo})는 band_high_hz({hi})보다 작아야 합니다.")
    if float(_param(params, "k")) <= 0:
        raise ValueError("k는 양수여야 합니다.")
    if float(_param(params, "k_global")) < 0:
        raise ValueError("k_global은 0 이상이어야 합니다(0이면 전역 하한을 끈다).")
    if float(_param(params, "min_gap_sec")) <= 0:
        raise ValueError("min_gap_sec는 양수여야 합니다.")
    if float(_param(params, "local_window_sec")) <= 0:
        raise ValueError("local_window_sec는 양수여야 합니다.")
    if float(_param(params, "smooth_ms")) < 0:
        raise ValueError("smooth_ms는 0 이상이어야 합니다.")


def _moving_average(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1:
        return x
    kernel = np.ones(win, dtype=np.float64) / win
    return np.convolve(x, kernel, mode="same")


def _local_median_mad(x: np.ndarray, half_win: int) -> tuple[np.ndarray, np.ndarray]:
    """각 지점 ±half_win 구간의 median·MAD(중앙값절대편차).

    `scipy.ndimage.median_filter`로 벡터화한다(창마다 파이썬 루프로 직접
    median/MAD를 구하면 100초·48kHz 오디오에서 샘플당 반복이라 실용적인
    시간 안에 안 끝난다 — 실측: 4.8M 샘플에서 순수 루프 버전은 120초
    타임아웃). `mode="nearest"`로 경계를 있는 값으로 채워 창이 배열
    경계를 넘어가도 자연스럽게 처리한다.
    """
    size = 2 * half_win + 1
    median = ndimage.median_filter(x, size=size, mode="nearest")
    mad = ndimage.median_filter(np.abs(x - median), size=size, mode="nearest")
    return median, mad


def detect_beep_onsets(path: Path, params: dict[str, Any] | None = None) -> list[float]:
    """대역통과 + 지역 적응형 임계값으로 onset 시각(초) 목록을 찾는다.

    band가 나이퀴스트를 넘는 등 필터링이 불가능하면 빈 리스트를 반환한다
    (원본 샘플레이트가 예상보다 낮은 파일에 대한 안전장치).
    """
    params = params or {}
    validate_params(params)

    samples, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if samples.shape[0] == 0:
        return []

    mono = to_mono(samples, sr, channel="mean").samples.astype(np.float64)

    lo = float(_param(params, "band_low_hz"))
    hi = float(_param(params, "band_high_hz"))
    nyq = sr / 2
    if not (0 < lo < hi < nyq):
        return []

    sos = sig.butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    filtered = sig.sosfiltfilt(sos, mono)

    envelope = np.abs(sig.hilbert(filtered))

    smooth_ms = float(_param(params, "smooth_ms"))
    if smooth_ms > 0:
        win = max(1, int(round(sr * smooth_ms / 1000.0)))
        envelope = _moving_average(envelope, win)

    local_window_sec = float(_param(params, "local_window_sec"))
    half_win = max(1, int(round(sr * local_window_sec)))
    median, mad = _local_median_mad(envelope, half_win)

    k = float(_param(params, "k"))
    threshold = median + k * mad

    # 전역 하한을 함께 건다 — 경계에서 지역 통계가 무너져 임계값이 0에
    # 가까워지는 것을 막는다(DEFAULTS의 k_global 주석 참조).
    k_global = float(_param(params, "k_global"))
    if k_global > 0:
        global_median = float(np.median(envelope))
        global_mad = float(np.median(np.abs(envelope - global_median)))
        threshold = np.maximum(threshold, global_median + k_global * global_mad)

    min_gap_sec = float(_param(params, "min_gap_sec"))
    distance = max(1, int(round(sr * min_gap_sec)))

    peaks, _ = sig.find_peaks(envelope, height=threshold, distance=distance)

    return [round(float(p / sr), 3) for p in peaks]
