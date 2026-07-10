# 오디오 데이터셋 관리 플랫폼 (Audio Dataset Management Platform)

대학 연구실용, 여러 오디오 도메인(차량음·심음·산업음·음성 등)에 **설정만으로 재사용**되는
수집→커팅→메타데이터→데이터셋→통계 자동화 플랫폼. 상세 설계는 [`docs/`](docs/) 참조.

## 구조 (모노레포)

```
audio-platform/
├── backend/    FastAPI (Python 3.12, uv)
├── frontend/   Next.js (App Router, npm)
├── data/       로컬 저장소 (uploads/segments/exports) — git 제외
└── docs/       설계 문서 (PRD·아키텍처·구조·DB·API)
```

## 사전 준비
- **uv** (Python 패키지·버전 관리) — Python 3.12는 uv가 자동 설치
- **Node 18+ / npm**
- **ffmpeg** (mp3/flac/m4a 처리 시 필요; wav만 쓰면 없어도 동작) — `brew install ffmpeg`

## 백엔드 실행

```bash
cd backend
uv sync                              # 의존성 설치 (최초 1회)
uv run alembic upgrade head          # DB 스키마 적용 (M2 이후)
uv run uvicorn app.main:app --reload --port 8000
```

- API 문서(Swagger): http://localhost:8000/docs
- 헬스체크: http://localhost:8000/health

환경변수는 `.env.example`를 `backend/.env`로 복사해 조정(경로·DB URL). 기본값은 SQLite + `data/`.

## 프론트엔드 실행

```bash
cd frontend
npm install                          # 최초 1회
cp .env.local.example .env.local     # API 주소 설정
npm run dev                          # http://localhost:3000
```

## 테스트 (Audio Core)

```bash
cd backend && uv run pytest
```

## 개발 규칙
코드를 짜기 전 [`CLAUDE.md`](CLAUDE.md)의 원칙(P1~P4)과 폴더 배치 규칙을 반드시 따른다.
특히 **도메인 분기문 금지**, **계층 의존 방향 준수**, **models/schemas 분리**.
