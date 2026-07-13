"""Projects 라우트 (+ 중첩 datasets) — 06_API.md §3, §4.

라우트는 검증·직렬화만 하고 흐름은 Service에 위임한다(얇은 API 계층).
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage_dep
from app.storage.base import StorageBackend
from app.schemas.common import Page
from app.schemas.dataset import DatasetCreate, DatasetRead
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.dataset_service import DatasetService
from app.services.project_service import ProjectService

router = APIRouter(tags=["projects"])


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="프로젝트 생성 (도메인 설정 포함)",
)
def create_project(
    body: ProjectCreate, db: Session = Depends(get_db)
) -> ProjectRead:
    project = ProjectService(db).create(body)
    return ProjectRead.model_validate(project)


@router.get(
    "/projects",
    response_model=Page[ProjectRead],
    summary="프로젝트 목록",
)
def list_projects(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page[ProjectRead]:
    items, total = ProjectService(db).list(limit=limit, offset=offset)
    return Page(items=[ProjectRead.model_validate(p) for p in items], total=total)


@router.get(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="프로젝트 상세",
)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    return ProjectRead.model_validate(ProjectService(db).get(project_id))


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="프로젝트 설정 수정",
)
def update_project(
    project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)
) -> ProjectRead:
    return ProjectRead.model_validate(ProjectService(db).update(project_id, body))


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="프로젝트 전체 삭제 (confirm=프로젝트명 필수 — 하위 데이터·파일 포함)",
)
def delete_project(
    project_id: int,
    confirm: str = Query(..., description="실수 방지: 프로젝트 이름을 정확히 입력"),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_dep),
) -> None:
    ProjectService(db).delete(project_id, confirm=confirm, storage=storage)


# --- 중첩: 프로젝트의 데이터셋 ---


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetRead,
    status_code=status.HTTP_201_CREATED,
    summary="데이터셋 생성",
)
def create_dataset(
    project_id: int, body: DatasetCreate, db: Session = Depends(get_db)
) -> DatasetRead:
    dataset = DatasetService(db).create(project_id, body)
    return DatasetRead.model_validate(dataset)


@router.get(
    "/projects/{project_id}/datasets",
    response_model=Page[DatasetRead],
    summary="프로젝트의 데이터셋 목록",
)
def list_datasets(
    project_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page[DatasetRead]:
    items, total = DatasetService(db).list_by_project(
        project_id, limit=limit, offset=offset
    )
    return Page(
        items=[DatasetRead.model_validate(d) for d in items], total=total
    )
