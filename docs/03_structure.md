# 03 — 폴더 구조 설계 (Project Structure)

> **목적**: 02 아키텍처의 계층(API/Service/Audio Core/Repository/Storage)을 **실제 디렉터리와 파일**로
> 배치한다. Claude Code가 "이 코드를 어디에 둘지" 매번 헷갈리지 않도록, 폴더마다 **역할과 금지사항**을 못박는다.
> 연결 문서: 02_architecture.md → (이 문서) → 05_DB설계.md / 06_API설계.md

---

## 0. 최상위 구조 (모노레포: 백엔드 + 프론트 한 저장소)

```
audio-platform/
├── docs/                      # 설계 문서 (이 문서들). Claude Code의 지침서
│   ├── 01_PRD.md
│   ├── 02_architecture.md
│   ├── 03_structure.md
│   └── ...
├── backend/                   # FastAPI (Python) — 아래 1장에서 상세
├── frontend/                  # Next.js (React) — 아래 2장에서 상세
├── data/                      # 로컬 저장소 (업로드·세그먼트·CSV). git에는 안 올림
│   ├── uploads/               #   원본 녹음
│   ├── segments/              #   커팅 결과 wav
│   └── exports/               #   생성된 metadata.csv
├── CLAUDE.md                  # Claude Code 규칙 (07 문서에서 작성)
├── README.md
├── .gitignore                 # data/, *.db, node_modules 등 제외
└── .env.example               # 환경변수 템플릿 (경로/설정)
```

### 왜 모노레포인가
- 초심자에게 저장소가 두 개면 관리·동기화가 어렵다. 하나로 두고 `backend/`·`frontend/`로 나눈다.
- Claude Code가 프론트-백엔드 계약(API 형태)을 **한 저장소 안에서** 함께 보며 개발할 수 있다.
- 나중에 분리하고 싶으면 그때 떼어내도 늦지 않다.

### data/를 git에서 제외하는 이유
오디오는 용량이 크고 실험 산출물이다. 코드가 아니므로 git에 넣지 않는다(.gitignore).
V2에서 이 폴더가 Google Drive로 대체된다 → 그래서 코드가 **경로가 아니라 Storage 인터페이스**로 접근해야 한다(02.6.1).

---

## 1. 백엔드 구조 (backend/) — 계층이 폴더가 된다

```
backend/
├── app/
│   ├── main.py                # FastAPI 앱 생성·라우터 등록·CORS. "시작점"
│   │
│   ├── api/                   # ── [API Layer] 웹만 안다 ──────────────
│   │   ├── deps.py            #   공통 의존성 (DB 세션 주입 등)
│   │   └── routes/
│   │       ├── projects.py    #   /projects  엔드포인트
│   │       ├── datasets.py    #   /datasets
│   │       ├── uploads.py     #   /uploads
│   │       ├── processing.py  #   /datasets/{id}/process, /jobs
│   │       └── stats.py       #   /stats (대시보드용)
│   │
│   ├── services/             # ── [Service Layer] 흐름을 지휘 ─────────
│   │   ├── upload_service.py      #   업로드→메타추출→등록
│   │   ├── processing_service.py  #   커팅 오케스트레이션(전략 호출)
│   │   ├── dataset_service.py     #   데이터셋·CSV 생성
│   │   └── stats_service.py       #   통계 집계 (AI Assistant도 재사용)
│   │
│   ├── audio/                # ── [Audio Core] 오디오만 안다 (웹·DB 모름) ─
│   │   ├── metadata.py            #   duration/sample_rate/channel/bit_depth...
│   │   ├── naming.py              #   naming_pattern → 파일명 생성
│   │   ├── normalize.py           #   정규화·포맷 변환
│   │   └── cutting/               #   ★ 전략 패턴 (재사용성 엔진)
│   │       ├── base.py            #     CutStrategy 인터페이스 + registry
│   │       ├── event.py           #     EventDetectionStrategy
│   │       ├── silence.py         #     SilenceDetectionStrategy
│   │       ├── fixed_interval.py  #     FixedIntervalStrategy
│   │       └── silence_based.py   #     SilenceBasedStrategy (무음 기준)
│   │
│   ├── repositories/         # ── [Repository Layer] DB 접근을 숨김 ────
│   │   ├── project_repo.py
│   │   ├── dataset_repo.py
│   │   ├── segment_repo.py
│   │   └── history_repo.py        #   upload/processing 이력
│   │
│   ├── storage/             # ── [Storage Backend] 교체 가능한 저장소 ──
│   │   ├── base.py              #   StorageBackend 인터페이스
│   │   ├── local.py            #   LocalStorage (주 저장소)
│   │   ├── drive.py            #   ★ V2-3 GoogleDriveStorage (Drive REST 미러, docs/09)
│   │   └── mirror.py           #   ★ V2-3 MirrorStorage (로컬 동기 + Drive 비동기 미러)
│   │
│   ├── hooks/               # ── [확장 지점] 이벤트 훅 + V2 구독자 ────────
│   │   ├── events.py           #   on_project_created / on_upload_complete ...
│   │   ├── notion.py           #   ★ V2-1 Notion 구독자 (docs/07, 토큰 없으면 no-op)
│   │   └── README.md          #   "V2에서 Notion/Drive를 여기에 구독시킨다"
│   │
│   ├── models/             # ── DB 테이블 정의 (SQLAlchemy ORM) ───────
│   │   ├── project.py
│   │   ├── dataset.py
│   │   ├── segment.py
│   │   ├── history.py
│   │   └── job.py
│   │
│   ├── schemas/            # ── 입출력 형태 정의 (Pydantic) ───────────
│   │   ├── project.py         #   API 요청/응답 검증용. models와 분리!
│   │   ├── dataset.py
│   │   └── segment.py
│   │
│   ├── core/              # ── 설정·공통 ────────────────────────────
│   │   ├── config.py         #   .env 로드, 경로/DB URL 등 (pydantic-settings)
│   │   └── database.py       #   DB 엔진·세션 (SQLite→PostgreSQL은 URL만 교체)
│   │
│   └── background/       # ── 비동기 작업 ──────────────────────────
│       └── worker.py        #   커팅 Job 실행 (MVP: BackgroundTasks, V2: Celery)
│
├── alembic/                 # DB 마이그레이션 (SQLite→PostgreSQL 전환 관리)
├── scripts/                 # 운영 도구 (1회성 설정 등)
│   └── setup_drive_auth.py  #   V2-3 Drive OAuth 1회 설정 (docs/09 §2)
├── tests/                   # Audio Core는 웹 없이 여기서 단독 테스트 가능
│   ├── test_cutting.py
│   └── test_naming.py
├── pyproject.toml           # uv/Poetry 의존성
└── .env
```

### 핵심 배치 규칙 (Claude Code가 지킬 것)
1. **의존 방향은 한쪽으로만**: `api → services → (audio / repositories / storage)`.
   반대로 audio가 api를 import 하면 안 된다. (층이 뒤엉키면 재사용 불가)
2. **audio/ 안에서는 web·DB import 금지**. 순수 파이썬 + 오디오 라이브러리만.
   → 그래서 노트북·테스트에서 그대로 돌아간다.
3. **models(ORM) 과 schemas(Pydantic)를 분리**한다. DB 테이블과 API 형태는 다른 관심사다.
   초심자가 가장 자주 뒤섞는 부분이라 폴더로 강제 분리.
4. **새 커팅 방식은 `audio/cutting/`에 파일 추가 + registry 등록만**. 다른 폴더 건드리지 않는다.

### 이 배치가 아키텍처와 1:1 대응하는지 확인
| 02 계층 | 폴더 |
|---|---|
| API Layer | `app/api/` |
| Service Layer | `app/services/` |
| Audio Core | `app/audio/` |
| Repository | `app/repositories/` |
| Storage Backend | `app/storage/` |
| 확장 훅 | `app/hooks/` |
| 비동기 Job | `app/background/` |

---

## 2. 프론트엔드 구조 (frontend/) — 대시보드 중심

Next.js App Router 기준. 초심자용으로 표준·단순 구성을 따른다.

```
frontend/
├── app/                      # Next.js App Router (페이지 = 폴더)
│   ├── layout.tsx            #   공통 레이아웃 (사이드바 + 헤더)
│   ├── page.tsx              #   대시보드 (홈)
│   ├── projects/
│   │   ├── page.tsx          #   프로젝트 목록
│   │   └── [id]/page.tsx     #   프로젝트 상세 (데이터셋·세그먼트)
│   ├── upload/page.tsx       #   업로드 화면
│   └── datasets/[id]/page.tsx#   데이터셋 상세
│
├── components/               # 재사용 UI 조각
│   ├── dashboard/
│   │   ├── StatCard.tsx      #   "총 파일 수" 같은 KPI 카드
│   │   ├── DistributionBar.tsx   #   Sample Rate/형식 분포 막대
│   │   └── RecentUploads.tsx
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   └── Header.tsx
│   └── ui/                   #   버튼·인풋 등 공통 프리미티브
│
├── lib/
│   ├── api.ts                #   백엔드 REST 호출 모음 (한 곳에 집중)
│   └── types.ts              #   백엔드 스키마와 맞춘 타입
│
├── styles/
│   └── globals.css           #   Tailwind + Grayish-Blue 테마 토큰
├── tailwind.config.ts        #   색상 팔레트 정의 (밝은 테마·회청색)
├── package.json
└── .env.local                #   NEXT_PUBLIC_API_URL 등
```

### 프론트 배치 규칙
- **모든 백엔드 호출은 `lib/api.ts` 한 곳**에서. 컴포넌트가 직접 fetch 하지 않는다.
  → API 주소·형태가 바뀌어도 한 파일만 고치면 된다(초심자 유지보수).
- **테마 색은 `tailwind.config.ts`에 토큰으로** 정의. 컴포넌트에 색상 하드코딩 금지.
  → Grayish-Blue 미니멀 톤을 일관되게 유지.
- 페이지는 얇게, 로직은 컴포넌트/lib로. 대시보드 중심 정보 UI(화려한 애니메이션 지양).

---

## 3. 이 구조가 주는 실질적 이득 (요약)

- **길 잃지 않음**: "커팅 코드? → `audio/cutting/`", "새 API? → `api/routes/` + `services/`"처럼
  질문이 곧 위치로 답해진다. Claude Code의 코드 배치가 일관돼진다.
- **부품 교체 자유**: 저장소·DB·비동기 방식이 각자 폴더에 격리 → V2 승격이 국소 변경으로 끝난다.
- **테스트·노트북 재사용**: `audio/`가 독립적이라 연구용 스크립트로도 바로 쓴다.
- **확장 자리 가시화**: `storage/drive.py`, `hooks/`가 빈 골격으로 존재 → "여기에 V2가 온다"가 눈에 보인다.

---

## 다음 단계
폴더가 정해졌으니, 그 안에 들어갈 **데이터의 모양**을 정의한다.
→ (권장) **07 CLAUDE.md**를 먼저 써서 지금까지의 규칙을 Claude Code가 항상 읽게 고정한 뒤,
   **05 DB 설계**로 models/ 안의 테이블(Project/Dataset/Segment/History/Job)을 확정한다.
