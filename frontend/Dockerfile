# NAS(시놀로지) 자체 호스팅용 프론트 이미지 — Vercel 배포와 무관하게 별도 존재.
# 빌드 컨텍스트 = 저장소 루트 (백엔드 Dockerfile과 동일 규칙).
#
# Next.js standalone 출력을 쓴다 — node_modules 전체 대신 필요한 것만 담아
# 이미지가 작아지고, NAS의 제한된 자원에서 기동이 빠르다.
FROM node:20-slim AS builder

WORKDIR /app

# 의존성 레이어 분리 (코드만 바뀌면 npm ci 캐시 재사용)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .

# 빌드 시점에 API 주소가 번들에 박힌다(NEXT_PUBLIC_*).
# NAS에서는 같은 호스트의 백엔드를 가리키므로 compose가 값을 넣어준다.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_REQUIRE_AUTH
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_REQUIRE_AUTH=$NEXT_PUBLIC_REQUIRE_AUTH

RUN npm run build

# --- 실행 이미지 ---
FROM node:20-slim AS runner

WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# standalone 출력물 + 정적 자원만 복사
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
