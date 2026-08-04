import { NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth";

/** 만료/변경된 토큰 정리 (docs/13 §6).
 *
 * 잘못된 토큰 쿠키를 지우고 로그인으로 보낸다. api.ts의 401 처리가 여기로
 * 보낸다 — 쿠키를 지우지 않고 /login으로 직행하면 미들웨어가 "토큰 있음"으로
 * 판단해 /로 되돌려 무한 루프가 된다 (실사고: 토큰 교체 후 Application error).
 */
export function GET(request: Request) {
  const res = NextResponse.redirect(new URL("/login", request.url));
  res.cookies.delete(TOKEN_COOKIE);
  return res;
}
