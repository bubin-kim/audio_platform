"""Datasets(+Segment 라벨) 라우트 — 06_API.md §4, §8."""

import re
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage_dep
from app.background.worker import run_export_job
from app.schemas.common import Page
from app.schemas.dataset import DatasetRead
from app.schemas.job import JobRead
from app.schemas.segment import LabelUpdate, SegmentRead, WaveformRead
from app.services.dataset_service import DatasetService
from app.services.segment_service import SegmentService
from app.storage.base import StorageBackend

router = APIRouter(tags=["datasets"])

# 브라우저 <audio>가 인식하는 media type. 목록에 없는 포맷은 octet-stream으로 내린다.
_AUDIO_MEDIA_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
}


@router.get(
    "/datasets/{dataset_id}",
    response_model=DatasetRead,
    summary="데이터셋 상세",
)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)) -> DatasetRead:
    return DatasetRead.model_validate(DatasetService(db).get(dataset_id))


@router.get(
    "/datasets/{dataset_id}/export",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Metadata.csv 내보내기 (비동기)",
)
def export_dataset(
    dataset_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobRead:
    job = DatasetService(db).start_export(dataset_id)
    background_tasks.add_task(run_export_job, job_id=job.id)
    return JobRead.model_validate(job)


@router.get(
    "/datasets/{dataset_id}/export/download",
    summary="가장 최근 완료된 Metadata.csv 다운로드",
)
def download_export(
    dataset_id: int,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> Response:
    service = DatasetService(db)
    job = service.get_latest_export_job(dataset_id)
    content = storage.read(job.result_path)
    filename = _export_filename(service.get(dataset_id).project.name)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


def _export_filename(project_name: str) -> str:
    """다운로드 파일명 = <프로젝트명>_metadata.csv (파일명에 못 쓰는 문자는 _로)."""
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", project_name).strip("_")
    return f"{safe}_metadata.csv" if safe else "metadata.csv"


def _content_disposition(filename: str) -> str:
    """HTTP 헤더는 latin-1만 허용되므로 한글 파일명은 RFC 5987(filename*)로 싣는다."""
    ascii_fallback = (
        filename.encode("ascii", "ignore").decode().lstrip("_") or "metadata.csv"
    )
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )


@router.get(
    "/datasets/{dataset_id}/segments",
    response_model=Page[SegmentRead],
    summary="세그먼트 목록",
)
def list_segments(
    dataset_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page[SegmentRead]:
    items, total = DatasetService(db).list_segments(
        dataset_id, limit=limit, offset=offset
    )
    return Page(items=[SegmentRead.model_validate(s) for s in items], total=total)


@router.get(
    "/segments/{segment_id}/audio",
    summary="세그먼트 오디오 재생 (브라우저 <audio>용 inline 스트림)",
)
def get_segment_audio(
    segment_id: int,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> Response:
    segment = SegmentService(db).get(segment_id)
    content = storage.read(segment.storage_path)
    return Response(
        content=content,
        media_type=_AUDIO_MEDIA_TYPES.get(segment.format, "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{segment.filename}"',
            # 세그먼트 파일은 생성 후 불변이라 캐시해도 안전하다.
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get(
    "/segments/{segment_id}/waveform",
    response_model=WaveformRead,
    summary="세그먼트 미니 파형 피크 (시각적 비교용)",
)
def get_segment_waveform(
    segment_id: int,
    response: Response,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> WaveformRead:
    segment, peaks = SegmentService(db).waveform(segment_id, storage)
    # 세그먼트 파일은 생성 후 불변 → 오디오 스트림과 동일하게 캐시 허용.
    response.headers["Cache-Control"] = "private, max-age=3600"
    return WaveformRead(
        segment_id=segment.id, duration_sec=segment.duration_sec, peaks=peaks
    )


@router.delete(
    "/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="데이터셋 전체 삭제 (confirm=데이터셋명 필수 — 세그먼트·원본·CSV 포함)",
)
def delete_dataset(
    dataset_id: int,
    confirm: str = Query(..., description="실수 방지: 데이터셋 이름을 정확히 입력"),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> None:
    DatasetService(db).delete_dataset(dataset_id, confirm=confirm, storage=storage)


@router.delete(
    "/segments/{segment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="세그먼트 1개 삭제 (파일 포함)",
)
def delete_segment(
    segment_id: int,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> None:
    SegmentService(db).delete(segment_id, storage)


@router.patch(
    "/segments/{segment_id}/labels",
    response_model=SegmentRead,
    summary="세그먼트 라벨 수정 (개별 예외 보정용)",
)
def update_segment_labels(
    segment_id: int, body: LabelUpdate, db: Session = Depends(get_db)
) -> SegmentRead:
    segment = SegmentService(db).update_labels(segment_id, body.labels)
    return SegmentRead.model_validate(segment)
