"""Uploads 라우트 — 06_API.md §5.

multipart/form-data. 파일을 읽어 Service에 넘기고, Service가 저장·메타추출·등록을 조립한다.
"""

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage_dep
from app.core.config import get_settings
from app.core.exceptions import PayloadTooLargeError
from app.schemas.common import Page
from app.schemas.segment import (
    BandSpectrogramRead,
    BeepOnsetsRead,
    SpectrogramRead,
    WaveformRead,
)
from app.schemas.upload import SourceRead, UploadResult
from app.services.dataset_service import DatasetService
from app.services.upload_service import UploadedFile, UploadService
from app.storage.base import StorageBackend

router = APIRouter(tags=["uploads"])


@router.post(
    "/uploads",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="원본 오디오 업로드 (+ 메타 자동 추출)",
)
async def upload_files(
    files: list[UploadFile] = File(..., description="하나 이상의 오디오 파일"),
    project_id: int = Form(..., description="대상 프로젝트"),
    dataset_id: int | None = Form(None, description="대상 데이터셋(없으면 v1 자동생성)"),
    uploaded_by: str | None = Form(
        None, max_length=100, description="업로드한 연구원 이름(선택, 자기 신고)"
    ),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> UploadResult:
    uploaded = [
        UploadedFile(filename=f.filename or "unnamed", data=await f.read())
        for f in files
    ]
    # 업로드 총 크기 상한 (docs/13 §7). 대형 파일 최적화는 비목표 — 정책으로 관리.
    limit_mb = get_settings().max_upload_mb
    total_mb = sum(len(u.data) for u in uploaded) / (1024 * 1024)
    if total_mb > limit_mb:
        raise PayloadTooLargeError(
            f"업로드 총 {total_mb:.0f}MB가 상한 {limit_mb:.0f}MB를 넘습니다. "
            "파일을 나눠 올리거나 관리자에게 MAX_UPLOAD_MB 조정을 요청하세요."
        )
    ds_id, created, sources = UploadService(db, storage).register_uploads(
        project_id=project_id,
        files=uploaded,
        dataset_id=dataset_id,
        uploaded_by=uploaded_by,
    )
    return UploadResult(
        dataset_id=ds_id,
        created_dataset=created,
        sources=[SourceRead.model_validate(s) for s in sources],
    )


@router.delete(
    "/source-files/{source_file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="원본 파일 삭제 (참조 세그먼트 있으면 409)",
)
def delete_source_file(
    source_file_id: int,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> None:
    DatasetService(db).delete_source_file(source_file_id, storage)


@router.get(
    "/datasets/{dataset_id}/sources",
    response_model=Page[SourceRead],
    summary="데이터셋의 원본 파일 목록 (docs/16 — 원본 섹션)",
)
def list_dataset_sources(
    dataset_id: int,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> Page[SourceRead]:
    sources = UploadService(db, storage).list_sources(dataset_id)
    items = [SourceRead.model_validate(s) for s in sources]
    return Page(items=items, total=len(items))


@router.get(
    "/source-files/{source_file_id}/spectrogram",
    response_model=SpectrogramRead,
    summary="원본 통 음원 멜 스펙트로그램 (docs/16)",
)
def get_source_spectrogram(
    source_file_id: int,
    response: Response,
    mode: str = Query(
        "absolute",
        pattern="^(absolute|contrast)$",
        description="absolute=실제 소리 크기 / contrast=배경 제거(묻힌 이벤트 탐색)",
    ),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> SpectrogramRead:
    spec = UploadService(db, storage).source_spectrogram(source_file_id, mode=mode)
    # 원본 파일은 불변 → 캐시 허용 (waveform과 동일 정책)
    response.headers["Cache-Control"] = "private, max-age=3600"
    return SpectrogramRead(
        duration_sec=spec.duration_sec, sample_rate=spec.sample_rate,
        n_mels=spec.n_mels, cols=spec.cols, fmax=spec.fmax,
        db_floor=spec.db_floor, db_ceil=spec.db_ceil, data=spec.data_b64,
    )


@router.get(
    "/source-files/{source_file_id}/waveform",
    response_model=WaveformRead,
    summary="원본 전체 파형 피크 (docs/16 — 원본 섹션 시각화)",
)
def get_source_waveform(
    source_file_id: int,
    response: Response,
    bins: int = Query(1200, ge=60, le=4000, description="가로 해상도(구간 수)"),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> WaveformRead:
    duration, peaks = UploadService(db, storage).source_waveform(source_file_id, bins=bins)
    # 원본 파일은 불변 → 캐시 허용 (세그먼트 파형과 동일 정책)
    response.headers["Cache-Control"] = "private, max-age=3600"
    return WaveformRead(segment_id=source_file_id, duration_sec=duration, peaks=peaks)


@router.get(
    "/source-files/{source_file_id}/band-spectrogram",
    response_model=BandSpectrogramRead,
    summary="원본 통 음원 주파수 크롭 스펙트로그램 (신규, 표시 전용 — 좁은 대역 확대)",
)
def get_source_band_spectrogram(
    source_file_id: int,
    response: Response,
    fmin: float = Query(1500.0, ge=0, description="크롭할 하한 주파수(Hz)"),
    fmax: float = Query(2500.0, gt=0, description="크롭할 상한 주파수(Hz)"),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> BandSpectrogramRead:
    spec = UploadService(db, storage).source_band_spectrogram(
        source_file_id, fmin=fmin, fmax=fmax
    )
    response.headers["Cache-Control"] = "private, max-age=3600"
    return BandSpectrogramRead(
        duration_sec=spec.duration_sec, sample_rate=spec.sample_rate,
        freq_bins=spec.freq_bins, cols=spec.cols, fmin=spec.fmin, fmax=spec.fmax,
        top_db=spec.top_db, data=spec.data_b64,
    )


@router.get(
    "/source-files/{source_file_id}/beep-onsets",
    response_model=BeepOnsetsRead,
    summary="원본 통 음원 대역통과 기반 비프음 onset 검출 (신규, 표시 전용)",
)
def get_source_beep_onsets(
    source_file_id: int,
    response: Response,
    band_low_hz: float | None = Query(None, description="대역통과 하한(Hz), 생략 시 기본값"),
    band_high_hz: float | None = Query(None, description="대역통과 상한(Hz), 생략 시 기본값"),
    k: float | None = Query(None, gt=0, description="지역 적응형 임계값 배수(median+k*MAD), 생략 시 기본값"),
    k_global: float | None = Query(None, ge=0, description="전역 하한 배수(경계 오탐 방어), 0이면 끔. 생략 시 기본값"),
    min_gap_sec: float | None = Query(None, gt=0, description="피크 간 최소 간격(초), 생략 시 기본값"),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> BeepOnsetsRead:
    summary = UploadService(db, storage).source_beep_onsets(
        source_file_id,
        band_low_hz=band_low_hz, band_high_hz=band_high_hz,
        k=k, k_global=k_global, min_gap_sec=min_gap_sec,
    )
    response.headers["Cache-Control"] = "private, max-age=3600"
    return BeepOnsetsRead(**summary)
