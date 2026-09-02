"""주파수 크롭 스펙트로그램 — 좁은 대역만 확대해서 보는 시각화 (순수 로직, P2).

`spectrogram.py`(멜 스케일, 전대역)와 달리 이 모듈은:
  - **선형(linear) STFT** — 멜이 아니다. 좁은 대역(예: 1900~2100Hz)을 볼
    때는 멜의 로그 압축이 오히려 대역 폭을 더 좁아 보이게 만든다.
  - **주파수 축을 [fmin, fmax] 구간만 잘라 세로 전체 높이에 채운다** —
    100Hz~16kHz 전체를 한 화면에 그리면 관심 대역이 몇 픽셀만 차지해
    육안 확인이 안 된다는 문제(차량 비프음 1900~2100Hz 협대역)를 푼다.

`mel_spectrogram()`(spectrogram.py)은 이 모듈이 전혀 건드리지 않는다 —
기존 두 탭("실제 크기"/"배경 제거")은 100% 그대로 동작한다.
"""

import base64
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from app.audio.channels import to_mono


@dataclass
class BandSpectrogramData:
    """주파수 크롭 스펙트로그램 + 렌더링에 필요한 메타."""

    duration_sec: float
    sample_rate: int
    freq_bins: int
    cols: int
    fmin: float
    fmax: float
    top_db: float
    data_b64: str  # uint8 (freq_bins × cols, 행 0=fmin), row-major, 0~255=0~top_db 아래로


def crop_band_spectrogram(
    path: Path,
    *,
    fmin: float = 1500.0,
    fmax: float = 2500.0,
    n_fft: int = 4096,
    hop_length: int = 512,
    top_db: float = 60.0,
    max_cols: int = 800,
) -> BandSpectrogramData:
    """선형 STFT를 계산하고 [fmin, fmax] 구간의 주파수 빈만 잘라 반환한다.

    dB 변환은 `librosa.amplitude_to_db(top_db=...)` — 신호의 최대값 기준
    top_db 아래를 클리핑하는 표준 방식(파일마다 적응형 범위를 쓰는
    mel_spectrogram과 다르게, 다이나믹 레인지를 고정해 여러 파일을 같은
    기준으로 비교하기 쉽게 한다).

    n_fft=4096·hop_length=512로 계산하면 100초 파일이 열 9천 개를 넘어
    base64 페이로드가 1MB를 넘는다 — **정밀 계산 후 응답 직전에만**
    `max_cols`로 다운샘플링한다(계산 자체의 시간·주파수 해상도는 그대로
    유지, mel_spectrogram의 max_cols 관례와 동일한 자리에서 압축).
    """
    if fmin < 0 or fmax <= fmin:
        raise ValueError(f"fmin({fmin})은 0 이상, fmax({fmax})보다 작아야 합니다.")
    if n_fft <= 0 or hop_length <= 0:
        raise ValueError("n_fft·hop_length는 양수여야 합니다.")
    if top_db <= 0:
        raise ValueError(f"top_db는 양수여야 합니다. 받은 값: {top_db!r}")
    if max_cols <= 0:
        raise ValueError(f"max_cols는 양수여야 합니다. 받은 값: {max_cols!r}")

    samples, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = to_mono(samples, sr).samples
    n = mono.shape[0]
    if n == 0:
        return BandSpectrogramData(
            duration_sec=0.0, sample_rate=sr, freq_bins=0, cols=0,
            fmin=fmin, fmax=fmax, top_db=top_db, data_b64="",
        )

    nyq = sr / 2
    effective_fmax = min(fmax, nyq)
    if fmin >= effective_fmax:
        # 요청 대역이 나이퀴스트 밖 — 빈 결과로 안전하게 반환
        return BandSpectrogramData(
            duration_sec=n / sr, sample_rate=sr, freq_bins=0, cols=0,
            fmin=fmin, fmax=fmax, top_db=top_db, data_b64="",
        )

    stft = librosa.stft(mono, n_fft=n_fft, hop_length=hop_length, window="hann")
    mag = np.abs(stft)
    db = librosa.amplitude_to_db(mag, ref=np.max, top_db=top_db)

    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band_idx = np.where((freqs >= fmin) & (freqs <= effective_fmax))[0]
    if band_idx.size == 0:
        return BandSpectrogramData(
            duration_sec=n / sr, sample_rate=sr, freq_bins=0, cols=0,
            fmin=fmin, fmax=fmax, top_db=top_db, data_b64="",
        )
    cropped = db[band_idx, :]

    if cropped.shape[1] > max_cols:
        # 열을 max_cols 구간으로 묶어 각 구간의 최대값을 대표값으로 쓴다
        # (평균이 아니라 최대값 — 짧은 비프음이 여러 열에 걸쳐 흐려지지
        # 않고 살아남게, event_detection의 "평균 아닌 최대" 결정과 같은
        # 이유, docs/17 §2i).
        edges = np.linspace(0, cropped.shape[1], max_cols + 1, dtype=np.int64)
        cropped = np.stack(
            [cropped[:, edges[i]:edges[i + 1]].max(axis=1) for i in range(max_cols)],
            axis=1,
        )

    # top_db 클리핑 후 실제 값 범위는 [max-top_db, max] — 0~255로 양자화.
    ceil = float(cropped.max())
    floor = ceil - top_db
    quant = np.round(np.clip((cropped - floor) / top_db * 255, 0, 255)).astype(np.uint8)

    return BandSpectrogramData(
        duration_sec=n / sr,
        sample_rate=int(sr),
        freq_bins=quant.shape[0],
        cols=quant.shape[1],
        fmin=float(freqs[band_idx[0]]),
        fmax=float(freqs[band_idx[-1]]),
        top_db=top_db,
        data_b64=base64.b64encode(quant.tobytes()).decode("ascii"),
    )
