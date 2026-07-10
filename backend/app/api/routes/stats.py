"""Stats 라우트 — 06_API.md §9. 대시보드 전체/프로젝트별 지표."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.stats import StatsResponse
from app.services.stats_service import StatsService

router = APIRouter(tags=["stats"])


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="대시보드 통계 (전체, 또는 project_id로 범위 한정)",
)
def get_stats(
    project_id: int | None = Query(None, description="지정 시 해당 프로젝트로 한정"),
    db: Session = Depends(get_db),
) -> StatsResponse:
    return StatsService(db).get_stats(project_id=project_id)
