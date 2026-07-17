"""FastAPI 앱 시작점.

앱 생성 · CORS · 라우터 등록만 한다. 업무 로직은 services/에 있다(얇은 API 계층, 02 §2).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import access_token_guard
from fastapi.responses import JSONResponse

from app.api.routes import datasets, processing, projects, stats, uploads
from app.background.worker import recover_orphan_jobs
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.schemas.common import ErrorResponse

settings = get_settings()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # 기동 시 고아 Job 정리 (docs/12 A2) — 크래시로 남은 queued/running이
    # has_running 가드를 영구 발동시키는 것을 막는다.
    recover_orphan_jobs()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="오디오 수집→커팅→메타데이터→데이터셋→통계 자동화 플랫폼 (MVP)",
    lifespan=_lifespan,
)

# 공용 액세스 토큰 가드 (docs/13 §6) — ACCESS_TOKEN 미설정 시 no-op 통과.
app.middleware("http")(access_token_guard)

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

# --- V2 플러그인 구독자 등록 (미설정 시 no-op — docs/07) ---
from app.hooks.notion import register_notion_subscribers  # noqa: E402

register_notion_subscribers()

from app.hooks.ntfy import register_ntfy_subscribers  # noqa: E402

register_ntfy_subscribers()
