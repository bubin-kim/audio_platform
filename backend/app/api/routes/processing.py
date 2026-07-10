"""Processing / Job 라우트 — 06_API.md §6, §7.

POST /datasets/{id}/process 는 즉시 202 + JobRead를 반환하고, 실제 커팅은
background/worker.py 가 별도 세션으로 수행한다(02 §4 — HTTP 요청 내 동기 실행 금지).
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.background.worker import run_cutting_job
from app.schemas.common import Page
from app.schemas.job import JobRead, ProcessRequest
from app.services.job_service import JobService
from app.services.processing_service import ProcessingService

router = APIRouter(tags=["processing"])


@router.post(
    "/datasets/{dataset_id}/process",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="커팅 Job 시작 (비동기)",
)
def start_processing(
    dataset_id: int,
    background_tasks: BackgroundTasks,
    body: ProcessRequest | None = None,
    db: Session = Depends(get_db),
) -> JobRead:
    job = ProcessingService(db).start_cutting(dataset_id, body or ProcessRequest())
    background_tasks.add_task(run_cutting_job, job_id=job.id)
    return JobRead.model_validate(job)


@router.get(
    "/jobs/{job_id}",
    response_model=JobRead,
    summary="Job 상태·진행률 조회 (폴링)",
)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobRead:
    return JobRead.model_validate(JobService(db).get(job_id))


@router.get(
    "/datasets/{dataset_id}/jobs",
    response_model=Page[JobRead],
    summary="데이터셋의 Job 목록",
)
def list_jobs(
    dataset_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page[JobRead]:
    items, total = JobService(db).list_by_dataset(
        dataset_id, limit=limit, offset=offset
    )
    return Page(items=[JobRead.model_validate(j) for j in items], total=total)
