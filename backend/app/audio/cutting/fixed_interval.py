"""FixedIntervalStrategy — 고정 간격 분할 (MVP 첫 전략).

긴 녹음을 interval_sec 단위로 자른다. soundfile.blocks로 스트리밍 읽어
4시간짜리 파일도 한 조각씩만 메모리에 올린다.

params:
  - interval_sec (float, 필수, >0): 조각 길이(초).
  - drop_last_shorter_than_sec (float, 선택): 마지막 조각이 이보다 짧으면 버린다.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import soundfile as sf

from app.audio.cutting.base import CutStrategy, SegmentAudio, register_strategy


class FixedIntervalStrategy(CutStrategy):
    name = "fixed_interval"

    def validate_params(self, params: dict[str, Any]) -> None:
        interval = params.get("interval_sec")
        if not isinstance(interval, (int, float)) or interval <= 0:
            raise ValueError(
                "fixed_interval에는 양수 interval_sec가 필요합니다. "
                f"받은 값: {interval!r}"
            )

    def cut(self, source: Path, params: dict[str, Any]) -> Iterator[SegmentAudio]:
        self.validate_params(params)
        interval_sec = float(params["interval_sec"])
        drop_below = params.get("drop_last_shorter_than_sec")

        info = sf.info(str(source))
        sr = info.samplerate
        block_frames = max(1, int(round(interval_sec * sr)))

        index = 0
        start_frame = 0
        for block in sf.blocks(
            str(source), blocksize=block_frames, dtype="float32", always_2d=False
        ):
            n = block.shape[0]
            if n == 0:
                continue
            duration = n / sr
            # 마지막 짧은 조각 버리기(옵션).
            if drop_below is not None and duration < float(drop_below):
                break
            yield SegmentAudio(
                index=index,
                start_sec=start_frame / sr,
                end_sec=(start_frame + n) / sr,
                samples=block,
                sample_rate=sr,
            )
            index += 1
            start_frame += n


# import 시 registry 등록 (P1: registry 조회로 분기문 제거).
register_strategy(FixedIntervalStrategy())
