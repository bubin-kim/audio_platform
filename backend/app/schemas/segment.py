"""Segment 입출력 스키마 (Pydantic) — 06_API.md §4.2, §8."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WaveformRead(BaseModel):
    """세그먼트 미니 파형 데이터 (06_API.md §4.5).

    peaks는 풀스케일(1.0) 기준 절대 피크 — 세그먼트 간 높이 비교 가능.
    """

    segment_id: int
    duration_sec: float
    peaks: list[float]


class SpectrogramRead(BaseModel):
    """멜 스펙트로그램 데이터 (docs/16 — 원본·세그먼트 공용).

    data는 uint8(0~100) n_mels×cols 행렬의 base64 (row-major, 행 0=최저음).
    dB는 풀스케일 기준 절대값(db_floor~db_ceil) — 파일별 정규화 없음.
    """

    duration_sec: float
    sample_rate: int
    n_mels: int
    cols: int
    fmax: float
    db_floor: float
    db_ceil: float
    data: str


class BandSpectrogramRead(BaseModel):
    """주파수 크롭 스펙트로그램(선형 STFT, 좁은 대역 확대) — 표시 전용 신규 기능.

    기존 SpectrogramRead(멜 스케일 전대역)와 별개 스키마. data는
    uint8(0~255) freq_bins×cols 행렬의 base64(row-major, 행 0=fmin).
    dB는 top_db 기준 상대값(파일 최대값 대비 -top_db~0).
    """

    duration_sec: float
    sample_rate: int
    freq_bins: int
    cols: int
    fmin: float
    fmax: float
    top_db: float
    data: str


class BeepOnsetsRead(BaseModel):
    """대역통과 기반 비프음 onset 검출 결과 + 자체 정합성 검증 통계.

    라벨로 저장되지 않는 표시 전용 결과 — 화면에서 바로 확인하고
    끝나는 진단용 데이터다.
    """

    count: int
    onsets_sec: list[float]
    offsets_sec: list[float]
    offset_median_sec: float | None
    offset_stddev_sec: float
    gaps_sec: list[float]


class BandWaveformRead(BaseModel):
    """대역통과 파형 (docs/16 §7 추가8 — 비프 대역 탭 전용, 표시 전용).

    기존 WaveformRead(전대역 절대 스케일)와 **별개 스키마**다. peaks는
    자기 최대값 기준 0~1 정규화라 파일 간 절대 비교에는 쓸 수 없고,
    원래 레벨은 peak_abs로 따로 싣는다.
    """

    duration_sec: float
    peaks: list[float]
    peak_abs: float
    band_low_hz: float
    band_high_hz: float


class LabelUpdate(BaseModel):
    """개별 세그먼트 라벨 수정 요청 (06_API.md §8 — 예외 보정용).

    기존 labels 위에 부분 덮어쓰기(merge)된다. 병합 결과가 label_schema로 검증된다.
    """

    labels: dict[str, Any]


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    filename: str
    storage_path: str
    duration_sec: float
    sample_rate: int
    channels: int
    bit_depth: int | None
    file_size: int
    format: str
    source_start_sec: float
    labels: dict[str, Any]
    is_labeled: bool
    created_at: datetime
