#!/usr/bin/env bash
# 개발 서버 동시 실행 — 터미널 하나로 backend + frontend를 띄운다.
#   backend : uvicorn --reload (:8100)  — 파이썬 파일 저장 시 자동 재시작
#   frontend: next dev        (:3100)  — 저장 시 즉시 핫 리로드
# 종료: Ctrl-C 한 번이면 둘 다 내려간다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for port in 8100 3100; do
  if lsof -i ":$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "ERROR: 포트 $port 가 이미 사용 중입니다. 기존 서버를 먼저 종료하세요:"
    echo "  lsof -i :$port -sTCP:LISTEN"
    exit 1
  fi
done

if [ ! -f "$ROOT/frontend/.env.local" ]; then
  cp "$ROOT/frontend/.env.local.example" "$ROOT/frontend/.env.local"
  echo "frontend/.env.local 생성됨 (.env.local.example 복사)"
fi

echo "[dev] DB 마이그레이션..."
(cd "$ROOT/backend" && uv run alembic upgrade head)

echo "[dev] backend  → http://localhost:8100 (uvicorn --reload)"
(cd "$ROOT/backend" && exec uv run uvicorn app.main:app --reload --port 8100) &

echo "[dev] frontend → http://localhost:3100 (next dev)"
(cd "$ROOT/frontend" && exec npm run dev) &

# Ctrl-C(INT)/TERM 시 이 스크립트의 프로세스 그룹 전체를 종료한다.
# npm run dev가 낳는 detached next-server 자식까지 같은 그룹이라 함께 죽는다.
trap 'trap - INT TERM; echo; echo "[dev] 서버 종료 중..."; kill -- -$$ 2>/dev/null' INT TERM

wait
