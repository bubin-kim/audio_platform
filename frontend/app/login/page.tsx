"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { verifyToken } from "@/lib/api";
import { setClientToken } from "@/lib/auth";

/** 공용 액세스 토큰 입력 (docs/13 §6). 백엔드에 검증 후 쿠키에 저장한다. */
export default function LoginPage() {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setChecking(true);
    setError(null);
    const ok = await verifyToken(token.trim());
    if (ok) {
      setClientToken(token.trim());
      window.location.href = "/"; // 미들웨어 게이트 재평가를 위해 전체 이동
    } else {
      setError("토큰이 올바르지 않습니다. 연구실 공지의 액세스 토큰을 확인하세요.");
      setChecking(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4">
      <Card className="w-full max-w-sm">
        <h1 className="text-lg font-medium text-content">Audio Dataset Platform</h1>
        <p className="mt-1 text-sm text-content-muted">
          연구실 액세스 토큰을 입력하면 시작합니다.
        </p>
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3">
          <input
            type="password"
            required
            autoFocus
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="액세스 토큰"
            className="w-full rounded border border-border px-2 py-1.5 text-sm"
          />
          {error && <p className="text-sm text-status-error">{error}</p>}
          <Button type="submit" disabled={checking || token.trim() === ""}>
            {checking ? "확인 중..." : "입장"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
