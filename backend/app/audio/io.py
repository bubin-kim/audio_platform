"""오디오 파일 읽기/쓰기 헬퍼 (순수 오디오 I/O).

soundfile 사용을 한 곳에 모은다. metadata·cutting이 공유한다.
web·DB를 모른다(P2). 입출력은 순수 파일시스템 Path만 받는다(Storage는 Service가 해석).
"""

from pathlib import Path

import numpy as np
import soundfile as sf


def write_wav(
    path: Path,
    samples: np.ndarray,
    sample_rate: int,
    *,
    subtype: str = "PCM_16",
) -> None:
    """샘플 배열을 wav로 저장한다.

    samples: (frames,) 또는 (frames, channels) 형태. 기본 16-bit PCM으로 기록.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples, sample_rate, subtype=subtype)


def read_all(path: Path) -> tuple[np.ndarray, int]:
    """파일 전체를 (samples, sample_rate)로 읽는다(원본 sr 유지).

    전체 신호를 봐야 하는 전략(silence/event, V2)에서 쓴다.
    대용량 스트리밍이 필요한 fixed_interval은 soundfile.blocks를 직접 쓴다.
    """
    samples, sr = sf.read(str(path), dtype="float32", always_2d=False)
    return samples, sr
