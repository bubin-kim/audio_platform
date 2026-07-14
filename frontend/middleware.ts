import { NextResponse, type NextRequest } from "next/server";

/** 페이지 게이트 (docs/13 §6).
 *
 * NEXT_PUBLIC_REQUIRE_AUTH=true(배포 환경)일 때만 동작: 토큰 쿠키가 없으면
 * /login으로 보낸다. 토큰의 "유효성"은 여기서 검사하지 않는다 — 그건 모든 API
 * 요청마다 백엔드 가드가 한다(잘못된 토큰이면 401 → api.ts가 /login으로 복귀).
 * 로컬 개발(미설정)에서는 아무것도 하지 않는다.
 */
export function middleware(request: NextRequest) {
  if (process.env.NEXT_PUBLIC_REQUIRE_AUTH !== "true") {
    return NextResponse.next();
  }
  const hasToken = Boolean(request.cookies.get("access_token")?.value);
  const isLogin = request.nextUrl.pathname === "/login";
  if (!hasToken && !isLogin) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (hasToken && isLogin) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // 정적 자원(_next 등)은 게이트 대상이 아니다.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
