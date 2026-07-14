/** 공용 액세스 토큰 보관 (docs/13 §6).
 *
 * 프론트 도메인의 1st-party 쿠키에 저장한다 — Next 미들웨어(게이트)와 SSR fetch가
 * 같은 쿠키를 읽는다. 백엔드(다른 도메인)로는 쿠키가 아니라 Authorization 헤더/
 * 쿼리 토큰으로 전달한다(서드파티 쿠키 차단 회피).
 */

export const TOKEN_COOKIE = "access_token";

/** 클라이언트(브라우저)에서 토큰 읽기. 서버 컴포넌트에서는 next/headers 경유(api.ts). */
export function getClientToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const found = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${TOKEN_COOKIE}=`));
  return found ? decodeURIComponent(found.split("=").slice(1).join("=")) : undefined;
}

export function setClientToken(token: string): void {
  const maxAge = 60 * 60 * 24 * 30; // 30일
  document.cookie = `${TOKEN_COOKIE}=${encodeURIComponent(token)}; path=/; max-age=${maxAge}; samesite=lax`;
}

export function clearClientToken(): void {
  document.cookie = `${TOKEN_COOKIE}=; path=/; max-age=0`;
}
