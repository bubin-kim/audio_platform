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
8. **순음성 필터**: 후보마다 스펙트럼을 보고 대역 안 최대 파워가 대역
   밖 평균보다 tonality_db 이상 큰 것만 남긴다 ← 광대역 소리(문 닫힘·
   차량 통과) 제거. 실데이터에서 오탐 10개를 전부 걸러냈다(DEFAULTS 주석)
9. 피크 위치를 초 단위(소수점 3자리)로 반환
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
    # 순음성(tonality) 필터 — 후보 지점의 스펙트럼을 보고 "좁은 대역에
    # 몰린 순음인가"를 확인해 통과시킨다. 엔벨로프 크기만 보면 실제
    # 주차장 환경의 광대역 소리(문 닫힘·차량 통과·반향)도 대역 안에서
    # 에너지가 튀어 오탐이 된다.
    #
    # 실측 근거(NAS 실데이터 260818_001.WAV, 100초): 엔벨로프 검출만으로
    # 20개가 나왔는데 진짜 10 + 오탐 10이었다. 두 무리를 스펙트럼으로
    # 재보니 완전히 갈렸다 —
    #   진짜: 피크가 **전부 1992Hz**, 대역/대역밖 비 14.9~19.3dB
    #   오탐: 피크 1922~2086Hz로 흩어짐, 비 2.0~11.8dB
    # 실제 구현으로 임계값을 스윕한 결과 **14dB**에서 실데이터 진짜
    # 10/10·오탐 0, 합성 100초도 10개 유지. 12~13은 오탐이 1~2개 남고,
    # 16부터는 진짜를 놓치기 시작한다(9/10).
    "tonality_db": 14.0,
    # 순음성을 잴 창 길이(초) — 비프음 길이(100~300ms)에 맞춘다.
    "tonality_win_sec": 0.15,
    "min_gap_sec": 2.0,
    "local_window_sec": 2.0,
    "smooth_ms": 20.0,
    # --- 주기 모드 (period_sec > 0이면 켜진다) ---
    # 비프음이 **일정 주기로** 울리는 녹음이면, 지점마다 독립적으로
    # 임계값을 넘는지 보는 대신 "주기적으로 반복되는가"를 본다.
    #
    # 왜 필요한가(실측 2026-08-28, 1일차 54개 전수 검증):
    #   임계값 방식은 54개 중 정상이 6개뿐이었다(0개 검출 12개, 1~5개
    #   24개). 원인은 파일마다 신호 세기가 크게 다른 것 — 튜닝에 쓴
    #   260818_001은 배경 대비 강했지만, 거리·각도가 다른 파일은
    #   **진짜 비프음이 잡음 상위값보다 작다**(분리 여유 0.25~0.84배).
    #   단일 임계값으로는 원리적으로 분리할 수 없는 상태다.
    #
    #   반면 100초를 10초씩 접어 누적하면 신호는 10배로 쌓이고 잡음은
    #   √10배만 커진다. 실측 결과 접은 곡선의 대비가 3.7~64배로 뛰어,
    #   임계값 방식으로 0개였던 파일들(008·049·053)도 위상을 정확히
    #   찾았다(오차 0.00초). 9개 튜닝 파일 중 8개가 10/10 정확.
    #
    # 0이면 꺼진다(기존 임계값 방식). 주기를 모르는 데이터에는 쓰지 않는다.
    "period_sec": 0.0,
    # 주기 창 안에서 최대점을 찾을 반경(초). 위상이 조금씩 흔들려도
    # 따라가되, 너무 넓으면 옆 주기를 침범한다.
    "period_search_sec": 0.6,
    # 접어서 위상을 찾을 때 쓰는 국소 배경 제거 창(초).
    "period_baseline_sec": 2.0,
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
    if float(_param(params, "tonality_win_sec")) <= 0:
        raise ValueError("tonality_win_sec는 양수여야 합니다.")
    if float(_param(params, "min_gap_sec")) <= 0:
        raise ValueError("min_gap_sec는 양수여야 합니다.")
    if float(_param(params, "local_window_sec")) <= 0:
        raise ValueError("local_window_sec는 양수여야 합니다.")
    if float(_param(params, "smooth_ms")) < 0:
        raise ValueError("smooth_ms는 0 이상이어야 합니다.")
    if float(_param(params, "period_sec")) < 0:
        raise ValueError("period_sec는 0 이상이어야 합니다(0이면 주기 모드를 끈다).")
    if float(_param(params, "period_search_sec")) <= 0:
        raise ValueError("period_search_sec는 양수여야 합니다.")
    if float(_param(params, "period_baseline_sec")) <= 0:
        raise ValueError("period_baseline_sec는 양수여야 합니다.")


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


def _tonality_db(
    mono: np.ndarray, sr: int, center_sec: float, lo: float, hi: float, win_sec: float
) -> float:
    """이 지점이 '좁은 대역의 순음'인 정도 — 대역 최대 파워 / 대역 밖 평균 파워(dB).

    비프음처럼 한 주파수에 에너지가 몰린 소리는 이 값이 크고, 문 닫힘·
    차량 통과 같은 광대역 소리는 대역 밖에도 에너지가 퍼져 있어 작다.
    대역 밖은 저역(300~1500Hz)과 고역(2600~6000Hz)을 쓴다 — 타겟 대역
    바로 옆은 필터 스커트 영향이 있어 띄운다.
    """
    half = int(win_sec * sr / 2)
    a, b = max(0, int(center_sec * sr) - half), min(len(mono), int(center_sec * sr) + half)
    seg = mono[a:b]
    if seg.size < 256:
        return 0.0

    nperseg = min(2048, seg.size)
    freqs, power = sig.welch(seg, sr, nperseg=nperseg)
    in_band = (freqs >= lo) & (freqs <= hi)
    out_band = ((freqs >= 300) & (freqs <= 1500)) | ((freqs >= 2600) & (freqs <= 6000))
    if not in_band.any() or not out_band.any():
        return 0.0

    return float(
        10 * np.log10(power[in_band].max() / max(float(power[out_band].mean()), 1e-20))
    )


def _detect_periodic(
    envelope: np.ndarray,
    sr: int,
    *,
    period_sec: float,
    search_sec: float,
    baseline_sec: float,
) -> list[float]:
    """주기 누적으로 위상을 찾고, 각 주기 창의 최대점을 onset으로 잡는다.

    임계값을 쓰지 않는다 — "이 지점이 충분히 큰가"가 아니라 "주기적으로
    반복되는 위치는 어디인가"를 묻기 때문에, 신호가 잡음에 묻혀 있어도
    (분리 여유 < 1) 위치를 찾아낸다.

    절차:
      1. 국소 배경(이동 median)을 빼 상승분만 남긴다 — 배경 드리프트가
         접기 결과를 흐리지 않게.
      2. period_sec 단위로 잘라 겹쳐 평균낸다(folding). 신호는 매번 같은
         위치에 쌓이고 잡음은 서로 상쇄된다.
      3. 접은 곡선의 최대점 = 위상. 그 위상에서 ±search_sec 안의 실제
         최대점을 주기마다 하나씩 고른다.
    """
    base = ndimage.median_filter(
        envelope, size=int(sr * baseline_sec) | 1, mode="nearest"
    )
    rise = np.maximum(envelope - base, 0.0)

    period = int(period_sec * sr)
    cycles = len(rise) // period
    if period <= 0 or cycles < 2:
        return []

    folded = rise[: cycles * period].reshape(cycles, period).mean(axis=0)
    phase_idx = int(np.argmax(folded))

    half = max(1, int(search_sec * sr))
    onsets: list[float] = []
    for i in range(cycles):
        center = i * period + phase_idx
        a, b = max(0, center - half), min(len(rise), center + half)
        if b <= a:
            continue
        onsets.append(round(float((a + int(np.argmax(rise[a:b]))) / sr), 3))
    return onsets


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

    # 주기 모드 — 주기를 알고 있으면 임계값 없이 위상으로 찾는다(훨씬 강함).
    period_sec = float(_param(params, "period_sec"))
    if period_sec > 0:
        return _detect_periodic(
            envelope,
            sr,
            period_sec=period_sec,
            search_sec=float(_param(params, "period_search_sec")),
            baseline_sec=float(_param(params, "period_baseline_sec")),
        )

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

    # 순음성 필터 — 엔벨로프만으로는 광대역 소리(문 닫힘·차량 통과)가
    # 걸러지지 않는다. 후보마다 스펙트럼을 보고 좁은 대역 순음인지 확인.
    tonality_db = float(_param(params, "tonality_db"))
    if tonality_db > 0:
        win_sec = float(_param(params, "tonality_win_sec"))
        peaks = [
            p
            for p in peaks
            if _tonality_db(mono, sr, p / sr, lo, hi, win_sec) >= tonality_db
        ]

    return [round(float(p / sr), 3) for p in peaks]
