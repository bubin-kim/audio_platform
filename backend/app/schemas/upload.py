"""Upload 입출력 스키마 (Pydantic) — 06_API.md §5."""

from pydantic import BaseModel, ConfigDict


class SourceRead(BaseModel):
    """업로드된 원본(SourceFile)의 응답 형태."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    storage_path: str
    duration_sec: float | None
    sample_rate: int | None
    channels: int | None
    bit_depth: int | None
    file_size: int | None
    format: str | None


class UploadResult(BaseModel):
    """업로드 결과. 대상 Dataset과 등록된 원본 목록."""

    dataset_id: int
    created_dataset: bool  # 기본 Dataset을 자동 생성했는지
    sources: list[SourceRead]
