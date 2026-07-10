"""Uploads 라우트 — 06_API.md §5.

multipart/form-data. 파일을 읽어 Service에 넘기고, Service가 저장·메타추출·등록을 조립한다.
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage_dep
from app.schemas.upload import SourceRead, UploadResult
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
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> UploadResult:
    uploaded = [
        UploadedFile(filename=f.filename or "unnamed", data=await f.read())
        for f in files
    ]
    ds_id, created, sources = UploadService(db, storage).register_uploads(
        project_id=project_id, files=uploaded, dataset_id=dataset_id
    )
    return UploadResult(
        dataset_id=ds_id,
        created_dataset=created,
        sources=[SourceRead.model_validate(s) for s in sources],
    )
