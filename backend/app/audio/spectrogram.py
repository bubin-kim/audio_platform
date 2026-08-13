"""멜 스펙트로그램 추출 — 원본/세그먼트 시각화용 (순수 오디오 로직, P2. docs/16).

주파수 축은 멜(로그) 스케일 — 저음~고음 어느 도메인에도 유효해 도메인 설정이
필요 없다(P1).

**표시 dB 범위는 파일 내용에 맞춰 정한다**: 고정 -80~0을 쓰면 실제 분포가
좁은 녹음(예: -55~+24)에서 대비가 죽어 환경음에 묻힌 이벤트가 안 보인다
(실측 2026-08-05: 260804_005.WAV는 하위 25dB가 아예 미사용, 상위는 클리핑).
바닥(p5)~정점(p99.5)을 범위로 잡되, 실제 쓰인 범위를 응답(db_floor/db_ceil)에
담아 보내므로 화면에서 절대 dB를 그대로 읽을 수 있다.
"""

import base64
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from app.audio.channels import to_mono

MIN_DB_SPAN = 30.0  # 표시 범위 최소 폭 (무음 파일에서 잡음이 과장되는 것 방지)
N_MELS = 128  # 주파수 해상도 (스크립트 검토 결과 96→128, 대역 구분이 또렷해짐)


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


def mel_spectrogram(
    path: Path, *, max_cols: int = 800, mode: str = "absolute"
) -> SpectrogramData:
    """파일 전체의 멜 스펙트로그램을 max_cols 이하 열로 계산한다.

    hop을 길이에 비례해 잡아 긴 파일도 열 수가 상한을 넘지 않는다.
    hop이 기본 FFT 창(2048)보다 커지면 창도 함께 키워 구간 누락을 막는다.

    mode:
      - "absolute": 절대 dB 그대로. 소리의 실제 크기를 본다.
      - "contrast": 주파수별 배경(중앙값)을 뺀 상대 dB. **환경음에 묻힌 이벤트를
        찾는 용도** — 저주파 환경음이 항상 더 커서 절대 모드에서는 이벤트가
        영영 안 보이는 녹음이 있다 (실측 2026-08-05, 260804_005.WAV: 경적
        순간에도 저주파가 경적보다 11~13dB 큼. 하지만 경적 대역 자체는 평소보다
        +9~12dB 올라가므로 배경을 빼면 드러난다).
    """
    if max_cols <= 0:
        raise ValueError(f"max_cols는 양수여야 합니다. 받은 값: {max_cols!r}")
    if mode not in ("absolute", "contrast"):
        raise ValueError(f"mode는 absolute|contrast 여야 합니다. 받은 값: {mode!r}")

    samples, sr = sf.read(str(path), dtype="float32", always_2d=True)
    # 다채널은 가장 또렷한 채널을 고른다 — 검출(event_detection)과 같은 신호를
    # 봐야 화면과 커팅 결과가 일치한다 (app/audio/channels.py 참조).
    mono = to_mono(samples, sr).samples
    n = mono.shape[0]
    if n == 0:
        return SpectrogramData(
            duration_sec=0.0, sample_rate=sr, n_mels=N_MELS, cols=0,
            fmax=sr / 2, db_floor=-MIN_DB_SPAN, db_ceil=0.0, data_b64="",
        )

    hop = max(512, -(-n // max_cols))  # ceil — 열 수가 max_cols를 넘지 않게
    n_fft = max(2048, _next_pow2(hop))

    mel = librosa.feature.melspectrogram(
        y=mono, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=N_MELS, fmax=sr / 2
    )
    db = librosa.power_to_db(mel, ref=1.0)  # 절대 dB

    if mode == "contrast":
        # 주파수별 배경(중앙값)을 빼서 "평소 대비 얼마나 올랐나"만 남긴다.
        # 항상 큰 저주파 환경음은 자기 배경에 묻히고, 간헐적 이벤트만 튄다.
        db = db - np.median(db, axis=1, keepdims=True)

    # 표시 범위: 이 파일의 바닥~정점. 정점은 p99.5(스파이크 1~2칸에 범위를
    # 통째로 뺏기지 않게), 바닥은 p5. 너무 좁으면(무음 파일 등) 최소 폭 보장.
    floor = float(np.percentile(db, 5))
    ceil = float(np.percentile(db, 99.5))
    if ceil - floor < MIN_DB_SPAN:
        ceil = floor + MIN_DB_SPAN

    clipped = np.clip(db, floor, ceil)
    quant = np.round((clipped - floor) / (ceil - floor) * 100).astype(np.uint8)
    quant = quant[:, :max_cols]  # 경계 반올림 방어

    return SpectrogramData(
        duration_sec=n / sr,
        sample_rate=int(sr),
        n_mels=N_MELS,
        cols=quant.shape[1],
        fmax=sr / 2,
        db_floor=round(floor, 1),
        db_ceil=round(ceil, 1),
        data_b64=base64.b64encode(quant.tobytes()).decode("ascii"),
    )
