"""EventDetectionStrategy — 이벤트를 탐지해 앞뒤 여유와 함께 잘라낸다 (docs/17).

정해진 초마다 자르는 fixed_interval과 달리 **소리가 나는 지점만** 골라낸다.
환경음(아파트·백화점)에 묻힌 경보음처럼, 전대역 음량으로는 안 보이는 이벤트를
좁은 대역의 **에너지 튐(prominence)**으로 찾는다.

**신호를 변형하지 않는다 (핵심 제약)**
밴드패스·스펙트럴 게이팅 같은 잡음 제거는 쓰지 않는다. 대역 선택은 STFT 결과에서
해당 주파수 빈만 **읽는** 것이라 신호 자체는 그대로다. 그리고 잘라 저장하는 것은
언제나 **원본 샘플**이다 — 판단에만 가공(리샘플·dB 변환)을 쓰고, 결과물은 원본.

**알고리즘** (사용자 청취 GT로 검증, 2026-08-13):
```
1. 채널 평균 (mean)                      ← GT 검증: ch3 단독 35.5% < mean 58.1%
2. 리샘플 48k → 44.1k (scipy.signal.resample)
3. STFT (nperseg=2048, noverlap=1024)
4. 타겟 대역(1900~2100Hz) dB의 프레임별 평균
5. baseline diff = 현재값 - 앞뒤 25프레임(자기 제외) median
6. find_peaks(diff, height=5.0, distance=4초)
7. 각 피크 center 기준 **원본**에서 [center-3초, center+3초] 커팅
```

**검증 결과** (tolerance 1.5초):

| 파일 | GT | TP | FP | FN | Recall | Precision |
|---|---|---|---|---|---|---|
| 004 | 31 | 24 | 7 | 7 | 77.4% | 77.4% |
| 005 | 35 | 28 | 4 | 7 | 80.0% | 87.5% |

남은 FN 원인은 ① 지속 노이즈로 prominence가 깎이는 경우 ② 두 이벤트가
min_gap_sec보다 가까워 하나로 병합되는 구조적 한계다(docs/17).

params (전부 Project 설정 — 도메인 값은 코드에 없다, P1):
  - before_sec (3.0) / after_sec (3.0): 이벤트 앞뒤 여유
  - band_low_hz (1900) / band_high_hz (2100): 탐지할 대역 (읽기만 — 필터링 아님)
  - height_db (5.0): baseline 대비 튐 임계
  - min_gap_sec (4.0): 이벤트 간 최소 간격
  - baseline_frames (51): baseline median 창 (자기 프레임 제외)
  - analysis_sr (44100): 분석용 리샘플 목표. 0/None이면 원본 샘플레이트 그대로
  - channel ("mean"): 채널 결합 방식
  - segment_sec / pre_pad_sec: 주면 before/after 대신 이 값으로 (기존 설정 호환)
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal as sig

from app.audio.channels import to_mono
from app.audio.cutting.base import CutStrategy, SegmentAudio, register_strategy

DEFAULTS: dict[str, Any] = {
    "before_sec": 3.0,
    "after_sec": 3.0,
    "band_low_hz": 1900.0,
    "band_high_hz": 2100.0,
    "height_db": 5.0,
    "min_gap_sec": 4.0,
    "baseline_frames": 51,
    "analysis_sr": 44100,
    "channel": "mean",
    "nperseg": 2048,
    "noverlap": 1024,
    # 주기 재탐색 (선택) — 이벤트가 규칙적으로 반복되는 녹음에서 지속 노이즈에
    # 묻힌 것을 건진다. 기본은 꺼짐(불규칙한 도메인에서는 오탐만 늘기 때문).
    "periodic_rescue": False,
    "rescue_tolerance_sec": 1.5,
}


@dataclass
class DetectedEvent:
    """탐지된 이벤트 하나 — 시점과 그때의 튐 정도(dB)."""

    center_sec: float
    prominence_db: float
    #: 주기 재탐색으로 건진 것인지 (1차 임계는 못 넘었다는 뜻 — 확인 우선순위 높음)
    rescued: bool = False


class EventDetectionStrategy(CutStrategy):
    name = "event_detection"

    def _param(self, params: dict[str, Any], key: str) -> Any:
        value = params.get(key)
        return DEFAULTS[key] if value is None else value

    def validate_params(self, params: dict[str, Any]) -> None:
        for key in ("before_sec", "after_sec"):
            if float(self._param(params, key)) < 0:
                raise ValueError(f"{key}는 0 이상이어야 합니다.")

        seg = params.get("segment_sec")
        if seg is not None and float(seg) <= 0:
            raise ValueError(f"segment_sec는 양수여야 합니다. 받은 값: {seg!r}")
        if seg is None and (
            float(self._param(params, "before_sec"))
            + float(self._param(params, "after_sec"))
            <= 0
        ):
            raise ValueError("before_sec + after_sec가 0보다 커야 합니다.")

        lo = float(self._param(params, "band_low_hz"))
        hi = float(self._param(params, "band_high_hz"))
        if lo < 0:
            raise ValueError(f"band_low_hz는 0 이상이어야 합니다. 받은 값: {lo!r}")
        if lo >= hi:
            raise ValueError(
                f"band_low_hz({lo})는 band_high_hz({hi})보다 작아야 합니다."
            )

        if float(self._param(params, "min_gap_sec")) <= 0:
            raise ValueError("min_gap_sec는 양수여야 합니다.")
        if int(self._param(params, "baseline_frames")) < 3:
            raise ValueError("baseline_frames는 3 이상이어야 합니다.")

    # --- 탐지 (판단용 신호 — 원본은 건드리지 않는다) ---

    def detect_events(
        self, source: Path, params: dict[str, Any]
    ) -> list[DetectedEvent]:
        """이벤트 목록. 커팅 없이 탐지만 — 미리보기·평가에서도 쓴다."""
        self.validate_params(params)
        samples, sr = sf.read(str(source), dtype="float32", always_2d=True)
        if samples.shape[0] == 0:
            return []

        mono = to_mono(samples, sr, channel=self._param(params, "channel")).samples

        # 분석용 리샘플 — 원본은 그대로 둔다(커팅은 원본에서)
        target_sr = self._param(params, "analysis_sr")
        if target_sr and int(target_sr) != sr:
            target_sr = int(target_sr)
            mono = sig.resample(mono, int(len(mono) * target_sr / sr))
        else:
            target_sr = sr

        diff, times = self._prominence_curve(mono, target_sr, params)
        if diff.size == 0 or len(times) < 2:
            return []

        dt = float(times[1] - times[0])
        distance = max(1, int(float(self._param(params, "min_gap_sec")) / dt))
        peaks, _ = sig.find_peaks(
            diff, height=float(self._param(params, "height_db")), distance=distance
        )
        events = [
            DetectedEvent(
                center_sec=float(times[p]),
                prominence_db=float(diff[p]),
                rescued=False,
            )
            for p in peaks
        ]

        if self._param(params, "periodic_rescue"):
            events.extend(self._rescue_periodic(diff, times, peaks, params))
            events.sort(key=lambda e: e.center_sec)
        return events

    def _rescue_periodic(
        self,
        diff: np.ndarray,
        times: np.ndarray,
        base_peaks: np.ndarray,
        params: dict[str, Any],
    ) -> list[DetectedEvent]:
        """규칙적 반복을 이용해 놓친 이벤트를 건진다.

        1차 탐지 결과에서 주기를 추정하고, 격자상 "있어야 하는데 비어 있는" 자리
        **주변만** 다시 본다. 임계를 전역으로 낮추지 않아 오탐 증가를 억제한다.

        실측 효과 (파일럿, GT 기준):

        | 파일 | 기존 Recall | 재탐색 후 | FN |
        |---|---|---|---|
        | 004 | 77.4% | **90.3%** | 7개 → 3개 |
        | 005 | 80.0% | **91.4%** | 7개 → 3개 |

        대신 FP가 늘어난다(004: 7→10, 005: 4→6). 놓치는 것보다 헛것을 사람이
        지우는 편이 나은 경우에만 켠다.
        """
        if len(base_peaks) < 3:
            return []  # 주기를 추정할 근거가 부족

        dt = float(times[1] - times[0])
        base_times = times[base_peaks]
        gaps = np.diff(base_times)
        gaps = gaps[gaps >= 2.0]  # 너무 붙은 간격은 주기 추정에서 제외
        if gaps.size == 0:
            return []

        # 주기는 간격의 중앙값. 배수 간격(놓친 자리)이 섞여도 중앙값은 기본
        # 주기에 수렴한다. ※ 잔차 최소화로 "정밀 추정"도 해봤으나 실측상 더
        # 나빴다(F1 81.2 → 78.9) — 신호의 실제 반복은 완전히 균일하지 않다.
        period = float(np.median(gaps))
        if period <= 0:
            return []

        # 격자 위상: 기존 피크들과의 오차가 최소가 되는 지점
        best_phase, best_err = 0.0, None
        for phase in np.arange(0, period, dt):
            k = np.round((base_times - phase) / period)
            err = float(np.abs(base_times - (phase + k * period)).mean())
            if best_err is None or err < best_err:
                best_err, best_phase = err, float(phase)

        tol = float(self._param(params, "rescue_tolerance_sec"))
        rescued: list[DetectedEvent] = []
        k = 0
        while best_phase + k * period <= times[-1]:
            center = best_phase + k * period
            k += 1
            if center < times[0]:
                continue
            if np.any(np.abs(base_times - center) <= tol):
                continue  # 이미 잡힌 자리

            lo = int(max(0, (center - tol) / dt))
            hi = int(min(len(diff), (center + tol) / dt + 1))
            if hi <= lo:
                continue
            j = lo + int(np.argmax(diff[lo:hi]))
            rescued.append(
                DetectedEvent(
                    center_sec=float(times[j]),
                    prominence_db=float(diff[j]),
                    rescued=True,
                )
            )
        return rescued

    def _prominence_curve(
        self, mono: np.ndarray, sr: int, params: dict[str, Any]
    ) -> tuple[np.ndarray, np.ndarray]:
        """대역 에너지가 국소 baseline보다 얼마나 튀는지(dB) 곡선.

        baseline은 **자기 프레임을 제외한** 앞뒤 median이다 — 이벤트 자신이
        baseline을 끌어올려 튐이 가려지는 것을 막는다.
        """
        nperseg = int(self._param(params, "nperseg"))
        noverlap = int(self._param(params, "noverlap"))
        freqs, times, zxx = sig.stft(mono, sr, nperseg=nperseg, noverlap=noverlap)
        db = 20 * np.log10(np.abs(zxx) + 1e-10)

        lo = float(self._param(params, "band_low_hz"))
        hi = float(self._param(params, "band_high_hz"))
        idx = np.where((freqs >= lo) & (freqs <= hi))[0]
        if idx.size == 0:  # 대역이 나이퀴스트 밖 — 전대역으로 폴백
            idx = np.arange(len(freqs))
        target_db = db[idx, :].mean(axis=0)

        n = len(target_db)
        half = int(self._param(params, "baseline_frames")) // 2
        diff = np.zeros(n)
        for i in range(n):
            lo_i, hi_i = max(0, i - half), min(n, i + half + 1)
            window = np.concatenate([target_db[lo_i:i], target_db[i + 1 : hi_i]])
            if window.size:
                diff[i] = target_db[i] - np.median(window)
        return diff, times

    # --- 커팅 (언제나 원본 샘플) ---

    def cut(self, source: Path, params: dict[str, Any]) -> Iterator[SegmentAudio]:
        self.validate_params(params)
        samples, sr = sf.read(str(source), dtype="float32", always_2d=True)
        total_sec = samples.shape[0] / sr if sr else 0.0
        if samples.shape[0] == 0:
            return

        before = float(self._param(params, "before_sec"))
        after = float(self._param(params, "after_sec"))
        if params.get("segment_sec") is not None:  # 기존 설정 호환
            length = float(params["segment_sec"])
            before = float(params.get("pre_pad_sec", length / 2))
            after = length - before

        for index, event in enumerate(self.detect_events(source, params)):
            start_sec = max(0.0, event.center_sec - before)
            end_sec = min(total_sec, event.center_sec + after)
            a, b = int(start_sec * sr), int(end_sec * sr)
            if b - a <= 0:
                continue
            yield SegmentAudio(
                index=index,
                start_sec=start_sec,
                end_sec=end_sec,
                samples=samples[a:b],  # ★ 원본 그대로 (가공 신호 아님)
                sample_rate=sr,
                detection={
                    "source_filename": source.name,
                    "detected_at_sec": round(event.center_sec, 3),
                    "prominence_db": round(event.prominence_db, 2),
                    "band_hz": [
                        float(self._param(params, "band_low_hz")),
                        float(self._param(params, "band_high_hz")),
                    ],
                    "height_db": float(self._param(params, "height_db")),
                    "channel": self._param(params, "channel"),
                    "rescued": event.rescued,
                },
            )


register_strategy(EventDetectionStrategy())
