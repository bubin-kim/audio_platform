"""멜 스펙트로그램 추출 — 원본/세그먼트 시각화용 (순수 오디오 로직, P2. docs/16).

주파수 축은 멜(로그) 스케일 — 저음~고음 어느 도메인에도 유효해 도메인 설정이
필요 없다(P1). dB는 풀스케일 기준 절대값(-80~0)을 0~100으로 양자화한다 —
파형과 같은 이유로 **파일별 정규화를 하지 않는다** (세그먼트끼리 밝기를 비교해
"비슷한 소리인지"를 눈으로 확인할 수 있어야 한다).
"""

import base64
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

DB_FLOOR = -80.0
DB_CEIL = 0.0
N_MELS = 96


@dataclass
class SpectrogramData:
    """양자화된 멜 스펙트로그램 + 렌더링에 필요한 메타."""

    duration_sec: float
    sample_rate: int
    n_mels: int
    cols: int
    fmax: float
    db_floor: float
    db_ceil: float
    data_b64: str  # uint8 (n_mels × cols, 행 0=최저음), row-major


def _next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


def mel_spectrogram(path: Path, *, max_cols: int = 800) -> SpectrogramData:
    """파일 전체의 멜 스펙트로그램을 max_cols 이하 열로 계산한다.

    hop을 길이에 비례해 잡아 긴 파일도 열 수가 상한을 넘지 않는다.
    hop이 기본 FFT 창(2048)보다 커지면 창도 함께 키워 구간 누락을 막는다.
    """
    if max_cols <= 0:
        raise ValueError(f"max_cols는 양수여야 합니다. 받은 값: {max_cols!r}")

    samples, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = samples.mean(axis=1)
    n = mono.shape[0]
    if n == 0:
        return SpectrogramData(
            duration_sec=0.0, sample_rate=sr, n_mels=N_MELS, cols=0,
            fmax=sr / 2, db_floor=DB_FLOOR, db_ceil=DB_CEIL, data_b64="",
        )

    hop = max(512, -(-n // max_cols))  # ceil — 열 수가 max_cols를 넘지 않게
    n_fft = max(2048, _next_pow2(hop))

    mel = librosa.feature.melspectrogram(
        y=mono, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=N_MELS, fmax=sr / 2
    )
    db = librosa.power_to_db(mel, ref=1.0)  # 절대 dB (파일별 정규화 없음)
    db = np.clip(db, DB_FLOOR, DB_CEIL)
    quant = np.round((db - DB_FLOOR) / (DB_CEIL - DB_FLOOR) * 100).astype(np.uint8)
    quant = quant[:, :max_cols]  # 경계 반올림 방어

    return SpectrogramData(
        duration_sec=n / sr,
        sample_rate=int(sr),
        n_mels=N_MELS,
        cols=quant.shape[1],
        fmax=sr / 2,
        db_floor=DB_FLOOR,
        db_ceil=DB_CEIL,
        data_b64=base64.b64encode(quant.tobytes()).decode("ascii"),
    )
