"""오디오 메타데이터 자동 추출 (F2).

파일 하나에서 duration/sample_rate/channels/bit_depth/file_size/format을 뽑는다.
순수 함수: 파일 Path만 받아 dataclass를 돌려준다(웹·DB 모름, P2).
"""

from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

# soundfile subtype → bit depth. 압축 포맷 등은 여기 없으면 None(의미 없음).
_SUBTYPE_BITS: dict[str, int] = {
    "PCM_S8": 8,
    "PCM_U8": 8,
    "PCM_16": 16,
    "PCM_24": 24,
    "PCM_32": 32,
    "FLOAT": 32,
    "DOUBLE": 64,
}


@dataclass
class AudioMetadata:
    duration_sec: float
    sample_rate: int
    channels: int
    bit_depth: int | None  # 압축 포맷(mp3 등)은 None
    file_size: int  # bytes
    format: str  # "wav", "mp3", ...


def extract_metadata(path: Path) -> AudioMetadata:
    """오디오 파일에서 메타데이터를 추출한다.

    wav/flac 등은 soundfile 헤더로 읽고, soundfile이 못 읽는 포맷은 librosa로 폴백한다.
    """
    path = Path(path)
    file_size = path.stat().st_size
    fmt = path.suffix.lstrip(".").lower()

    try:
        info = sf.info(str(path))
        duration = info.frames / info.samplerate if info.samplerate else 0.0
        return AudioMetadata(
            duration_sec=float(duration),
            sample_rate=int(info.samplerate),
            channels=int(info.channels),
            bit_depth=_SUBTYPE_BITS.get(info.subtype),
            file_size=file_size,
            format=fmt,
        )
    except (RuntimeError, sf.LibsndfileError):
        # 압축 포맷 폴백: librosa(→audioread/ffmpeg)로 sr·길이·채널만.
        import librosa

        y, sr = librosa.load(str(path), sr=None, mono=False)
        channels = 1 if y.ndim == 1 else int(y.shape[0])
        return AudioMetadata(
            duration_sec=float(librosa.get_duration(y=y, sr=sr)),
            sample_rate=int(sr),
            channels=channels,
            bit_depth=None,
            file_size=file_size,
            format=fmt,
        )
