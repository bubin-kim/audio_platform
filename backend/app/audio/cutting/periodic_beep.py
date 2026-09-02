"""PeriodicBeepStrategy — 주기 누적으로 비프음을 찾아 앞뒤 여유와 함께 자른다.

`event_detection`(임계값 방식)과 달리 **임계값을 쓰지 않는다.** 녹음
설계상 알고 있는 주기(예: 10초)를 이용해, 신호가 잡음에 묻혀 있어도
"주기적으로 반복되는 위치"를 찾아낸다.

**왜 필요한가** (실측 2026-08-28, 1일차 54개 전수 검증):
  임계값 방식은 정상이 7개(13%)뿐이었다 — 0개 검출 12개, 1~5개 24개.
  파일마다 신호 세기가 달라(거리·각도) **진짜 비프음이 잡음 상위값보다
  작은** 경우가 많았고(분리 여유 0.25~0.84배), 파라미터 100개 조합을
  전수 스윕해도 최선이 F1 65.1%였다 — 원리적으로 분리 불가능.

  주기 누적은 100초를 10초씩 접어 평균낸다. 신호는 같은 위치에 10배로
  쌓이고 잡음은 √10배만 커져 대비가 3.7~64배로 뛴다. **1일차 54/54,
  2일차 54/54** (오프셋 원형 표준편차 0.04~0.41초).

**한계**: 주기를 모르는 데이터에는 쓸 수 없다. 그런 경우
`event_detection`(임계값)이나 `fixed_interval`을 쓴다.

params (전부 Project 설정 — 도메인 값은 코드에 없다, P1):
  - period_sec (10.0): 비프음 주기. **이 값이 맞아야 동작한다.**
  - before_sec (3.0) / after_sec (3.0): 이벤트 앞뒤 여유
  - band_low_hz (1800) / band_high_hz (2200): 대역통과 범위
  - period_search_sec (0.6): 주기 창 안에서 최대점을 찾을 반경
  - period_baseline_sec (2.0): 위상 추정 시 국소 배경 제거 창
  - smooth_ms (20.0): 엔벨로프 스무딩
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import soundfile as sf

from app.audio.band_beep_detector import detect_beep_onsets
from app.audio.cutting.base import CutStrategy, SegmentAudio, register_strategy

DEFAULTS: dict[str, Any] = {
    "period_sec": 10.0,
    "before_sec": 3.0,
    "after_sec": 3.0,
    "band_low_hz": 1800.0,
    "band_high_hz": 2200.0,
    "period_search_sec": 0.6,
    "period_baseline_sec": 2.0,
    "smooth_ms": 20.0,
}


class PeriodicBeepStrategy(CutStrategy):
    name = "periodic_beep"

    def _param(self, params: dict[str, Any], key: str) -> Any:
        value = params.get(key)
        return DEFAULTS[key] if value is None else value

    def validate_params(self, params: dict[str, Any]) -> None:
        if float(self._param(params, "period_sec")) <= 0:
            raise ValueError("period_sec는 양수여야 합니다(주기를 알아야 쓸 수 있는 전략).")
        for key in ("before_sec", "after_sec"):
            if float(self._param(params, key)) < 0:
                raise ValueError(f"{key}는 0 이상이어야 합니다.")
        if (
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
            raise ValueError(f"band_low_hz({lo})는 band_high_hz({hi})보다 작아야 합니다.")

    def cut(self, source: Path, params: dict[str, Any]) -> Iterator[SegmentAudio]:
        self.validate_params(params)

        source = Path(source)  # 문자열로 들어와도 동작하게(테스트·스크립트 편의)
        samples, sr = sf.read(str(source), dtype="float32", always_2d=True)
        total_sec = samples.shape[0] / sr if sr else 0.0
        if samples.shape[0] == 0:
            return
        # 원본 해상도를 조각에도 유지한다(24bit 원본이 16bit로 떨어지면
        # 약한 신호의 양자화 여유가 크게 줄어든다 — event_detection과 동일 정책)
        src_subtype = sf.info(str(source)).subtype

        onsets = detect_beep_onsets(
            source,
            {
                "period_sec": float(self._param(params, "period_sec")),
                "band_low_hz": float(self._param(params, "band_low_hz")),
                "band_high_hz": float(self._param(params, "band_high_hz")),
                "period_search_sec": float(self._param(params, "period_search_sec")),
                "period_baseline_sec": float(self._param(params, "period_baseline_sec")),
                "smooth_ms": float(self._param(params, "smooth_ms")),
            },
        )

        before = float(self._param(params, "before_sec"))
        after = float(self._param(params, "after_sec"))

        for index, onset in enumerate(onsets):
            start_sec = max(0.0, onset - before)
            end_sec = min(total_sec, onset + after)
            a, b = int(start_sec * sr), int(end_sec * sr)
            if b - a <= 0:
                continue
            yield SegmentAudio(
                index=index,
                start_sec=start_sec,
                end_sec=end_sec,
                samples=samples[a:b],  # ★ 원본 그대로 (가공 신호 아님)
                sample_rate=sr,
                subtype=src_subtype,
                detection={
                    "source_filename": source.name,
                    "detected_at_sec": round(onset, 3),
                    "method": "periodic",
                    "period_sec": float(self._param(params, "period_sec")),
                    "band_hz": [
                        float(self._param(params, "band_low_hz")),
                        float(self._param(params, "band_high_hz")),
                    ],
                    # 위상(주기 안에서의 위치) — 검수 때 규칙성을 바로 볼 수 있다
                    "phase_sec": round(
                        onset % float(self._param(params, "period_sec")), 3
                    ),
                },
            )


register_strategy(PeriodicBeepStrategy())
