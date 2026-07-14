# 배포용 백엔드 이미지 (DP-M4, docs/13 §7) — Railway가 이 파일로 빌드한다.
# 로컬 개발은 이 파일과 무관하게 ./scripts/dev.sh 그대로 (docs/13 목표 3).
FROM python:3.12-slim

# ffmpeg: mp3/m4a 디코딩(pydub). libsndfile은 soundfile 휠에 포함.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv 바이너리만 공식 이미지에서 복사 (파이썬 재설치 없음)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 의존성 레이어 분리: 코드만 바뀌면 의존성 설치는 캐시 재사용
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# 단일 인스턴스 전제(docs/13 §10)라 시작 시 마이그레이션 경합 없음.
# $PORT는 Railway가 주입한다.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
