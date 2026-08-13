"""EventDetectionStrategy — 이벤트를 찾아 앞뒤 여유와 함께 고정 길이로 자른다 (docs/17).

정해진 초마다 자르는 fixed_interval과 달리, **소리가 나는 지점만** 골라낸다.
환경음이 커서 전대역 음량으로는 이벤트가 묻히는 녹음(파일럿 260804_004/005)을
위해, 좁은 주파수 대역에서 **국소 배경 대비 z-score**로 검출한다.

실측 근거 (2026-08-08, 사용자 청취 정답 기준):
- 004의 정답 5개(34/40/46/52/58초)에 대해 1900-2100Hz·z>4.0·간격3초로 **5/5 적중**,
  전체 31개 검출(실제 30개). 같은 설정을 005에 적용 시 32개 검출 + 확인된 경적 2곳
  모두 적중 → 과적합 아님.
- **구간 병합 방식이 아니라 봉우리(find_peaks) 단위**로 찾는 것이 핵심이었다.
  병합 방식은 긴 구간이 인접 이벤트를 삼켜 5개 중 2개만 잡혔다.
- 배경은 **국소 중앙값 + 국소 MAD**로 정규화한다. 004는 0~30초 배경이 -42.5dB,
  30초 이후가 -27.7dB로 15dB 차이 나서 전역 임계로는 앞 구간만 검출됐다.

params:
  - segment_sec (float, 필수, >0): 잘라낼 고정 길이.
  - pre_pad_sec (float, 기본 segment_sec/2): 이벤트 기준 앞쪽 여유.
  - band_low_hz / band_high_hz (float, 선택): 검출 대역. 없으면 전대역.
  - z_threshold (float, 기본 4.0): 국소 배경 대비 z-score 임계.
  - min_rise_db (float, 기본 5.0): 국소 배경 대비 최소 상승분(dB). z-score만
    쓰면 배경이 매우 균질한 구간에서 국소 MAD가 0에 가까워져 사소한 요동도
    큰 z가 된다 — 절대 상승분 하한으로 이를 막는다. 실파일(004/005)에서는
    3~6dB 어느 값이든 결과가 같아(31/32개, 정답 5/5) 안전한 기본값이다.
  - min_gap_sec (float, 기본 3.0): 이벤트 간 최소 간격(봉우리 분리 거리).
  - bg_window_sec (float, 기본 10.0): 국소 배경 추정 창.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
from scipy import ndimage, signal as sig

from app.audio.channels import to_mono
from app.audio.cutting.base import CutStrategy, SegmentAudio, register_strategy

_NFFT = 2048
_HOP = 512


class EventDetectionStrategy(CutStrategy):
    name = "event_detection"

    def validate_params(self, params: dict[str, Any]) -> None:
        seg = params.get("segment_sec")
        if not isinstance(seg, (int, float)) or seg <= 0:
            raise ValueError(
                "event_detection에는 양수 segment_sec가 필요합니다. "
                f"받은 값: {seg!r}"
            )
        lo = params.get("band_low_hz")
        hi = params.get("band_high_hz")
        if (lo is None) != (hi is None):
            raise ValueError(
                "band_low_hz와 band_high_hz는 함께 지정해야 합니다 "
                f"(받은 값: low={lo!r}, high={hi!r})."
            )
        if lo is not None and hi is not None and float(lo) >= float(hi):
            raise ValueError(
                f"band_low_hz({lo})는 band_high_hz({hi})보다 작아야 합니다."
            )

    def detect_events(self, source: Path, params: dict[str, Any]) -> list[float]:
        """이벤트 시각(초) 목록. 커팅 없이 검출만 — 진단·미리보기에서도 쓴다."""
        self.validate_params(params)
        samples, sr = sf.read(str(source), dtype="float32", always_2d=True)
        mono = self._to_mono(samples, sr, params)
        if mono.size == 0:
            return []

        z, rise = self._zscore_curve(mono, sr, params)
        dt = _HOP / sr
        distance = max(1, int(float(params.get("min_gap_sec", 3.0)) / dt))
        peaks, _ = sig.find_peaks(
            z, height=float(params.get("z_threshold", 4.0)), distance=distance
        )
        # 절대 상승분 하한 — 배경이 균질한 구간의 사소한 요동을 걸러낸다
        min_rise = float(params.get("min_rise_db", 5.0))
        return [float(i * dt) for i in peaks if rise[i] >= min_rise]

    def cut(self, source: Path, params: dict[str, Any]) -> Iterator[SegmentAudio]:
        self.validate_params(params)
        samples, sr = sf.read(str(source), dtype="float32", always_2d=True)
        mono = self._to_mono(samples, sr, params)
        total_sec = mono.shape[0] / sr if sr else 0.0
        if mono.size == 0:
            return

        segment_sec = float(params["segment_sec"])
        pre_pad = float(params.get("pre_pad_sec", segment_sec / 2))

        for index, event_sec in enumerate(self.detect_events(source, params)):
            start_sec = max(0.0, event_sec - pre_pad)
            end_sec = start_sec + segment_sec
            if end_sec > total_sec:
                # 파일 끝에 걸치면 뒤로 당겨 길이를 유지한다(고정 길이 계약).
                end_sec = total_sec
                start_sec = max(0.0, end_sec - segment_sec)
            a, b = int(start_sec * sr), int(end_sec * sr)
            if b - a <= 0:
                continue
            yield SegmentAudio(
                index=index,
                start_sec=start_sec,
                end_sec=end_sec,
                samples=samples[a:b],
                sample_rate=sr,
            )

    def _to_mono(
        self, samples: np.ndarray, sr: int, params: dict[str, Any]
    ) -> np.ndarray:
        """분석용 모노 신호. 다채널이면 검출 대역에서 가장 또렷한 채널을 고른다.

        단순 평균은 채널이 서로 다른 소리를 담을 때 신호를 희석시킨다
        (실측: 파일럿 4채널에서 평균 대비 +1.9~3.4dB 손해 — docs/17).
        """
        lo, hi = params.get("band_low_hz"), params.get("band_high_hz")
        band = (float(lo), float(hi)) if lo is not None and hi is not None else None
        return to_mono(
            samples, sr, channel=params.get("channel", "auto"), band=band
        ).samples

    def _zscore_curve(
        self, mono: np.ndarray, sr: int, params: dict[str, Any]
    ) -> tuple[np.ndarray, np.ndarray]:
        """대역 에너지의 국소 배경 대비 z-score 곡선.

        국소 중앙값을 빼고 국소 MAD로 나눈다 — 구간마다 배경 수준이 달라도
        '그 구간 기준으로 얼마나 이례적인가'라는 같은 잣대가 된다.
        """
        spec = np.abs(librosa.stft(mono, n_fft=_NFFT, hop_length=_HOP))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=_NFFT)

        lo = params.get("band_low_hz")
        hi = params.get("band_high_hz")
        if lo is not None and hi is not None:
            mask = (freqs >= float(lo)) & (freqs <= float(hi))
            if not mask.any():  # 대역이 나이퀴스트 밖이면 전대역으로 폴백
                mask = np.ones_like(freqs, dtype=bool)
        else:
            mask = np.ones_like(freqs, dtype=bool)

        band_db = 20 * np.log10(np.sqrt(np.mean(spec[mask] ** 2, axis=0)) + 1e-12)
        dt = _HOP / sr
        window = max(3, int(float(params.get("bg_window_sec", 10.0)) / dt) | 1)
        rise = band_db - ndimage.median_filter(band_db, size=window, mode="nearest")
        mad = ndimage.median_filter(np.abs(rise), size=window, mode="nearest")
        return rise / np.maximum(mad, 0.5), rise


register_strategy(EventDetectionStrategy())
