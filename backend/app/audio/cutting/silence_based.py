"""SilenceBasedStrategy — 무음 구간 기준 분할.

RMS 에너지가 threshold(dBFS) 미만인 상태가 min_silence_sec 이상 이어지면 무음으로
판정하고, 무음과 무음 사이의 소리 구간을 조각 하나로 잘라낸다.

soundfile.blocks 스트리밍으로 읽으며 현재 소리 구간(+padding)만 버퍼에 올린다.
max_segment_sec를 주면 버퍼 상한도 보장된다(무음이 전혀 없는 녹음 대비).

threshold는 절대값(dBFS)이다 — 파일 최대음량 대비 상대값이 아니라서, 같은 프로젝트
(같은 마이크·게인) 안에서 파일이 달라도 판정 기준이 흔들리지 않는다(재현성).

params (모두 선택 — 기본값만으로 동작):
  - silence_threshold_db (float, <0, 기본 -40.0): 이 값 미만이면 무음.
  - min_silence_sec (float, >0, 기본 0.3): 무음이 이보다 길어야 구분점으로 인정.
  - min_segment_sec (float, >=0, 기본 0.2): 이보다 짧은 조각은 버림(스파이크 제거).
  - max_segment_sec (float, >min_segment_sec, 기본 없음): 넘으면 강제로 자름.
  - padding_sec (float, >=0, 기본 0.1): 조각 앞뒤에 남기는 무음 여유.
    min_silence_sec/2를 넘으면 이웃 조각과 겹치므로 그 값으로 클램프.

프레임 크기는 내부 고정: 20ms 창을 10ms 간격으로 훑는다(파라미터로 노출하지 않음).
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.audio.cutting.base import CutStrategy, SegmentAudio, register_strategy

_FRAME_SEC = 0.02  # RMS 창 크기
_HOP_SEC = 0.01  # 창 이동 간격
_READ_BLOCK_SEC = 1.0  # 파일에서 한 번에 읽는 크기

_DEFAULTS: dict[str, float] = {
    "silence_threshold_db": -40.0,
    "min_silence_sec": 0.3,
    "min_segment_sec": 0.2,
    "padding_sec": 0.1,
}


class SilenceBasedStrategy(CutStrategy):
    name = "silence_based"

    def validate_params(self, params: dict[str, Any]) -> None:
        def _num(key: str) -> float | None:
            value = params.get(key)
            if value is None:
                return None
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"silence_based의 {key}는 숫자여야 합니다. 받은 값: {value!r}")
            return float(value)

        threshold = _num("silence_threshold_db")
        if threshold is not None and threshold >= 0:
            raise ValueError(
                f"silence_threshold_db는 음수(dBFS)여야 합니다. 받은 값: {threshold!r}"
            )
        min_silence = _num("min_silence_sec")
        if min_silence is not None and min_silence <= 0:
            raise ValueError(f"min_silence_sec는 양수여야 합니다. 받은 값: {min_silence!r}")
        min_segment = _num("min_segment_sec")
        if min_segment is not None and min_segment < 0:
            raise ValueError(f"min_segment_sec는 0 이상이어야 합니다. 받은 값: {min_segment!r}")
        padding = _num("padding_sec")
        if padding is not None and padding < 0:
            raise ValueError(f"padding_sec는 0 이상이어야 합니다. 받은 값: {padding!r}")
        max_segment = _num("max_segment_sec")
        if max_segment is not None:
            effective_min = min_segment if min_segment is not None else _DEFAULTS["min_segment_sec"]
            if max_segment <= effective_min:
                raise ValueError(
                    f"max_segment_sec({max_segment!r})는 min_segment_sec({effective_min!r})보다 커야 합니다."
                )

    def cut(self, source: Path, params: dict[str, Any]) -> Iterator[SegmentAudio]:
        self.validate_params(params)
        threshold_db = float(params.get("silence_threshold_db", _DEFAULTS["silence_threshold_db"]))
        min_silence_sec = float(params.get("min_silence_sec", _DEFAULTS["min_silence_sec"]))
        min_segment_sec = float(params.get("min_segment_sec", _DEFAULTS["min_segment_sec"]))
        padding_sec = min(
            float(params.get("padding_sec", _DEFAULTS["padding_sec"])), min_silence_sec / 2
        )
        max_segment = params.get("max_segment_sec")

        info = sf.info(str(source))
        sr = info.samplerate
        frame = max(1, int(round(_FRAME_SEC * sr)))
        hop = max(1, int(round(_HOP_SEC * sr)))
        threshold_amp = 10.0 ** (threshold_db / 20.0)
        min_silence_smp = int(round(min_silence_sec * sr))
        min_segment_smp = int(round(min_segment_sec * sr))
        max_segment_smp = int(round(float(max_segment) * sr)) if max_segment is not None else None
        pad_smp = int(round(padding_sec * sr))

        # 버퍼는 절대 샘플 인덱스로 관리한다: buf[i] = 원본의 (buf_start + i)번째 프레임.
        buf: np.ndarray | None = None
        buf_start = 0
        pos = 0  # 다음에 평가할 RMS 창의 시작(절대 인덱스)
        event_start: int | None = None  # 진행 중인 소리 구간 시작
        event_pad_head = True  # 구간 머리에 padding을 붙일지(강제 분할 직후엔 False)
        silence_start: int | None = None  # 소리 구간 안에서 이어지는 무음의 시작
        index = 0
        total_frames = 0

        def _slice(start: int, end: int) -> np.ndarray:
            assert buf is not None
            return buf[start - buf_start : end - buf_start]

        def _emit(
            core_start: int, core_end: int, *, pad_head: bool, pad_tail: bool
        ) -> SegmentAudio | None:
            """소리 구간 [core_start, core_end)를 padding 붙여 내보낸다. 너무 짧으면 None.

            강제 분할(max_segment) 지점은 무음이 아니므로 padding을 붙이지 않는다
            (붙이면 이웃 조각과 겹친다).
            """
            nonlocal index
            if core_end - core_start < min_segment_smp:
                return None
            seg_start = max(0, core_start - pad_smp, buf_start) if pad_head else core_start
            seg_end = min(total_frames, core_end + pad_smp) if pad_tail else core_end
            segment = SegmentAudio(
                index=index,
                start_sec=seg_start / sr,
                end_sec=seg_end / sr,
                samples=np.copy(_slice(seg_start, seg_end)),
                sample_rate=sr,
            )
            index += 1
            return segment

        read_block = max(frame, int(round(_READ_BLOCK_SEC * sr)))
        blocks = sf.blocks(str(source), blocksize=read_block, dtype="float32", always_2d=False)
        eof = False
        while True:
            # 다음 창을 평가할 만큼 버퍼를 채운다.
            while not eof and (buf is None or buf_start + len(buf) < pos + frame):
                try:
                    block = next(blocks)
                except StopIteration:
                    eof = True
                    break
                if buf is None or len(buf) == 0:
                    buf, buf_start = block, total_frames
                else:
                    buf = np.concatenate([buf, block])
                total_frames += block.shape[0]

            if buf is None:
                break  # 빈 파일
            if buf_start + len(buf) < pos + frame:
                break  # EOF: 남은 샘플이 창 하나도 안 됨 → 스캔 종료

            window = _slice(pos, pos + frame)
            rms = float(np.sqrt(np.mean(np.square(window), dtype=np.float64)))
            is_silent = rms < threshold_amp

            if event_start is None:
                if not is_silent:
                    event_start = pos
                    event_pad_head = True
                    silence_start = None
            else:
                if is_silent:
                    if silence_start is None:
                        silence_start = pos
                    elif pos + frame - silence_start >= min_silence_smp:
                        # 무음이 충분히 길다 → silence_start에서 구간 종료.
                        segment = _emit(
                            event_start, silence_start,
                            pad_head=event_pad_head, pad_tail=True,
                        )
                        if segment is not None:
                            yield segment
                        event_start = None
                        silence_start = None
                else:
                    silence_start = None

                # 강제 분할: 소리 구간이 max를 넘으면 자르고 이어서 진행.
                if (
                    event_start is not None
                    and max_segment_smp is not None
                    and pos + frame - event_start >= max_segment_smp
                ):
                    cut_at = event_start + max_segment_smp
                    segment = _emit(
                        event_start, cut_at, pad_head=event_pad_head, pad_tail=False
                    )
                    if segment is not None:
                        yield segment
                    event_start = cut_at  # 이어지는 소리는 새 조각으로
                    event_pad_head = False  # 분할 지점은 무음이 아님 → 머리 padding 없음
                    silence_start = None

            # 더 이상 필요 없는 앞부분을 버려 메모리를 묶는다.
            keep_from = (event_start if event_start is not None else pos) - pad_smp
            keep_from = max(buf_start, keep_from)
            if keep_from > buf_start:
                buf = buf[keep_from - buf_start :]
                buf_start = keep_from

            pos += hop

        # EOF 처리: 열려 있는 소리 구간을 마무리한다.
        if event_start is not None:
            core_end = silence_start if silence_start is not None else total_frames
            segment = _emit(
                event_start, core_end, pad_head=event_pad_head, pad_tail=True
            )
            if segment is not None:
                yield segment


# import 시 registry 등록 (P1: registry 조회로 분기문 제거).
register_strategy(SilenceBasedStrategy())
