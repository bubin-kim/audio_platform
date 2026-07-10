"""FastAPI 앱 시작점.

앱 생성 · CORS · 라우터 등록만 한다. 업무 로직은 services/에 있다(얇은 API 계층, 02 §2).
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import datasets, processing, projects, stats, uploads
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.schemas.common import ErrorResponse

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="오디오 수집→커팅→메타데이터→데이터셋→통계 자동화 플랫폼 (MVP)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """도메인 예외 → 06_API.md의 상태코드·ErrorResponse 형식으로 변환."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(detail=exc.message, code=exc.code).model_dump(),
    )


@app.get("/health", summary="헬스체크", tags=["system"])
def health() -> dict[str, str]:
    """서버가 살아있는지 확인하는 최소 엔드포인트."""
    return {"status": "ok"}


# --- 라우터 등록 (api prefix 하위) ---
app.include_router(projects.router, prefix=settings.api_prefix)
app.include_router(datasets.router, prefix=settings.api_prefix)
app.include_router(uploads.router, prefix=settings.api_prefix)
app.include_router(processing.router, prefix=settings.api_prefix)
app.include_router(stats.router, prefix=settings.api_prefix)
