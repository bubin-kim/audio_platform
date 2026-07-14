"""공용 액세스 토큰 가드 (docs/13 §6).

`ACCESS_TOKEN`이 설정된 경우에만 검사한다 — 비어 있으면 모든 요청을 그대로 통과
(로컬 개발은 기존과 100% 동일, P4 패턴). 미들웨어 자체는 항상 등록하고 요청 시점에
설정을 읽는다: 테스트에서 켜고 끄기 쉽고, 미설정 시 비용은 문자열 비교 1회뿐이다.

규칙 (06_API.md §2.5와 일치해야 함):
  - `/api/*` 요청은 `Authorization: Bearer <token>` 필요. 불일치 → 401.
  - 예외 1: `/api` 밖 경로(`/health`, Swagger 등)는 검사하지 않는다.
  - 예외 2: CORS preflight(OPTIONS)는 통과 (브라우저가 헤더를 못 붙이는 단계).
  - 예외 3: 미디어 URL(오디오/파형/CSV 다운로드)은 `?token=<token>` 쿼리도 허용
    — <audio src>·<a href>는 브라우저가 Authorization 헤더를 붙일 수 없다.
"""

import hmac

from fastapi import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

# 쿼리 토큰을 허용하는 경로 접미사 (헤더를 못 붙이는 브라우저 네이티브 로딩 대상)
_QUERY_TOKEN_SUFFIXES = ("/audio", "/waveform", "/export/download")


def _token_ok(expected: str, presented: str | None) -> bool:
    return presented is not None and hmac.compare_digest(expected, presented)


async def access_token_guard(request: Request, call_next):  # noqa: ANN001, ANN201
    """FastAPI http 미들웨어 본체. main.py에서 등록한다."""
    expected = get_settings().access_token
    if not expected:
        return await call_next(request)  # 인증 비활성 — 기존 동작 그대로

    path = request.url.path
    if not path.startswith("/api") or request.method == "OPTIONS":
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    bearer = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    if _token_ok(expected, bearer):
        return await call_next(request)

    if path.endswith(_QUERY_TOKEN_SUFFIXES) and _token_ok(
        expected, request.query_params.get("token")
    ):
        return await call_next(request)

    return JSONResponse(
        status_code=401,
        content={"detail": "액세스 토큰이 필요합니다.", "code": "UNAUTHORIZED"},
    )
