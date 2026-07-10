# 02 — 아키텍처 설계 (Architecture Design)

> **이 문서의 목적**: PRD(무엇을/왜)를 만족하는 **시스템 구조(어떻게)** 를 정의한다.
> 계층 분리·데이터 흐름·비동기 처리·확장 지점을 다룬다. 실제 폴더/코드는 03 이후 문서에서.
> 독자가 FastAPI/React 초심자임을 전제로, 각 선택의 **이유**를 함께 적는다.

- **버전**: v1.0 (MVP)
- **연결 문서**: 01_PRD.md → (이 문서) → 03_폴더구조.md → 07_CLAUDE.md

---

## 0. 이 아키텍처가 지켜야 하는 4대 원칙 (PRD에서 유래)

| 원칙 | 구조적 실현 방법 | 관련 PRD |
|---|---|---|
| P1. 도메인은 설정에 산다 | 커팅/명명/라벨을 **Project 설정**으로 분리, 코드는 전략(Strategy)만 실행 | G1, R1 |
| P2. 교체 가능한 부품 | Storage·DB를 **인터페이스**로 추상화 (구현체 교체) | R2, R3 |
| P3. 붙일 자리를 미리 | 주요 사건에 **이벤트 훅** → MCP/AI/Notion을 나중에 플러그인처럼 | R5 |
| P4. 초심자 유지보수 | **계층 분리** + 표준 패턴 + 자동 문서(Swagger) | R4, R6 |

> 이 4개가 이후 모든 구조적 결정의 근거다.

---

## 1. 전체 시스템 조감도 (High-Level)

```
┌──────────────────────────────────────────────────────────────┐
│                        사용자 (브라우저)                          │
└───────────────────────────────┬──────────────────────────────┘
                                 │  HTTP (REST + JSON)
                ┌────────────────▼─────────────────┐
                │      FRONTEND  (Next.js/React)     │
                │  - Dashboard  - Upload  - Project  │
                │  - Tailwind (Grayish-Blue, minimal)│
                └────────────────┬─────────────────┘
                                 │  REST API 호출
                ┌────────────────▼─────────────────────────────┐
                │            BACKEND (FastAPI, Python)           │
                │                                                │
                │   API Layer  (라우터 / 검증 / Swagger)          │
                │        │                                       │
                │   Service Layer  (업무 로직 / 오케스트레이션)      │
                │        │                                       │
                │   ┌────┴─────────────┬──────────────────┐      │
                │   │ Audio Core       │ Repository Layer  │      │
                │   │ (커팅/메타/정규화) │ (DB 접근 추상화)    │      │
                │   └────┬─────────────┴────────┬─────────┘      │
                │        │                      │                │
                │   Storage Backend        ORM (SQLAlchemy)      │
                │   (인터페이스)                 │                │
                └────────┼──────────────────────┼───────────────┘
                         │                      │
              ┌──────────▼─────┐        ┌───────▼────────┐
              │ Local FS (MVP) │        │ SQLite (MVP)   │
              │ →Drive (V2)    │        │ →PostgreSQL(V2)│
              └────────────────┘        └────────────────┘

   ┌───────────────── 확장(플러그인) 계층: MVP엔 비어있음 ─────────────┐
   │  Event Hooks →  Notion MCP · Google Drive MCP · GitHub MCP     │
   │  Tool Interface → AI Assistant (OpenAI/Claude API)             │
   │  Auth Middleware → JWT (교수/연구원/관리자)                       │
   └───────────────────────────────────────────────────────────────┘
```

**읽는 법**: 위→아래로 요청이 흐른다. 맨 아래 두 상자(저장소·DB)는 **교체 가능한 부품**이고,
맨 밑 점선 상자는 **지금은 비어 있지만 자리는 만들어 둔** 확장 계층이다.

---

## 2. 백엔드 계층 구조 (왜 나누는가)

FastAPI 백엔드를 4개 층으로 나눈다. 초심자에게 이 분리는 "귀찮아 보이지만 나중에 살려준다."

```
[ API Layer ]        HTTP 요청을 받고, 입력을 검증하고, 응답을 돌려준다.
     │               (예: POST /uploads 를 받는 곳)
     ▼               ⮕ "웹의 세계"만 안다. 오디오/DB는 모른다.
[ Service Layer ]    실제 업무 흐름을 조립한다.
     │               (예: "업로드되면 → 메타 추출 → 커팅 → 저장 → CSV")
     ▼               ⮕ 전체 시나리오의 지휘자.
[ Audio Core ]  +  [ Repository ]
     │                   │
 오디오 처리 순수 로직    DB 저장/조회 (SQL을 숨김)
 (librosa/pydub 등)     (SQLAlchemy)
```

### 왜 이렇게 나누나? — 구체적 이득
- **API Layer가 얇으면** 나중에 CLI나 AI Assistant가 같은 Service를 재사용할 수 있다.
  (예: "20m 데이터 몇 개?"라는 AI 질의도 결국 같은 Service 함수를 부른다.)
- **Audio Core가 웹/DB를 모르면** 그 커팅 로직을 주피터 노트북에서도, 테스트에서도 그대로 쓴다.
  → 연구실 특성상 "스크립트로도 돌리고 싶다"는 요구를 자연히 만족.
- **Repository가 SQL을 숨기면** SQLite→PostgreSQL 전환 시 Service를 안 고쳐도 된다(R3).

> 한 문장 요약: **"각 층은 자기 일만 안다."** 그래서 한 곳을 바꿔도 다른 곳이 안 무너진다.

---

## 3. 핵심 데이터 흐름 (업로드 → CSV → 대시보드)

MVP의 심장. 아래 흐름이 **모든 도메인에서 동일**하게 돈다.

```
(1) 업로드
    사용자가 파일/폴더 + Project 선택 → API Layer 수신
        │
(2) 원본 등록 & 메타 추출
    Audio Core가 duration/sample_rate/channel/bit_depth/size/created_time 추출
    Repository가 원본 파일 레코드 + Upload History 저장
        │
(3) 커팅 (백그라운드 작업으로)   ※ 4장 참조
    Project 설정의 cutting_strategy 로드
      ├ event    → Event Detection
      ├ silence  → Silence Detection
      └ fixed    → Fixed Interval
    → 여러 Segment 생성
        │
(4) 파일명 생성
    Project.naming_pattern + (라벨 + 자동메타) 로 각 Segment 파일명 결정
        │
(5) 저장
    Storage Backend가 Segment wav 저장 (Local FS)
    Repository가 Segment 메타데이터를 DB에 기록
    Processing History 기록
        │
(6) CSV 생성
    Dataset 단위로 Segment들을 Metadata.csv 로 내보내기
        │
(7) 이벤트 훅 발화  ※ V2-1: Notion 구독자가 듣는다 (docs/07). Drive/GitHub은 아직 빈 자리
        │
(8) 대시보드
    Frontend가 통계 API 호출 → 개수/시간/용량/분포 렌더링
```

**중요**: (3)의 분기(event/silence/fixed)만이 도메인마다 다르고, 나머지 (1)(2)(4)(5)(6)(8)은
**완전히 공통**이다. 즉 새 도메인이 와도 갈아끼우는 건 "전략 한 조각"뿐이다(P1).

---

## 4. 대용량 파일과 비동기 처리 (4시간 녹음 문제)

4시간 녹음을 커팅하면 수십 초~수 분이 걸린다. 이걸 HTTP 요청 안에서 처리하면
브라우저가 응답을 기다리다 타임아웃 난다. 그래서 **커팅은 백그라운드로 분리**한다.

```
사용자 → POST /datasets/{id}/process
            │
            ├─ 즉시 응답: { job_id, status: "queued" }   ← 사용자는 안 기다림
            │
            └─ 백그라운드에서 커팅 실행
                  status: queued → running → done / failed
                  진행률 갱신 (예: 320/1000 segments)

사용자 → GET /jobs/{job_id}   (폴링)  → 진행률/상태 확인 → 대시보드 진행바
```

### MVP의 현실적 선택
- **MVP**: FastAPI의 `BackgroundTasks` 또는 가벼운 인프로세스 워커로 시작.
  (Redis/Celery는 초심자에게 과함 — 안정성·학습난이도 기준 R7/R6에서 배제.)
- **V2 확장 지점**: 작업이 많아지면 Job 큐를 Celery+Redis로 승격.
  이를 위해 지금 **Job(작업) 개념을 DB에 모델링**해 둔다(Processing History와 연결).

> 원칙: "지금은 단순하게, 그러나 나중에 큐로 승격할 수 있게 Job을 1급 객체로 둔다."

---

## 5. 재사용성의 엔진 — 전략 패턴 (Strategy Pattern)

P1을 코드 구조로 구현하는 방법. 커팅 방식마다 클래스를 하나씩 만들고,
**공통 인터페이스**로 묶는다. Service는 "어떤 전략인지" 모른 채 그냥 호출한다.

```
        ┌────────────────────────┐
        │  CutStrategy (인터페이스) │   cut(audio, params) -> [Segment]
        └───────────┬────────────┘
        ┌───────────┼───────────────┐
        ▼           ▼               ▼
 EventDetection  SilenceDetection  FixedInterval
   Strategy         Strategy         Strategy

Service:  strategy = registry[project.cutting_mode]
          segments = strategy.cut(audio, project.params)   ← 분기문 없음!
```

### 왜 좋은가 (초심자용 설명)
- 새 커팅 방식(예: "심음용 R-peak 기반 분할")이 필요하면 **클래스 하나만 추가**하고 registry에 등록하면 끝.
  기존 코드는 한 줄도 안 건드린다.
- `if project == "차량음" ...` 같은 **도메인 분기문이 코드에 절대 안 생긴다.** 이게 종속성을 막는 핵심.
- 파일명 생성(naming), 라벨 스키마도 같은 원리로 "설정 주도"로 처리한다.

---

## 6. 교체 가능한 부품 — Storage & DB 추상화 (P2)

### 6.1 Storage Backend (Local → Drive)
```
        ┌──────────────────────────┐
        │ StorageBackend (인터페이스) │  save(path, bytes) / read(path) / list()
        └────────────┬─────────────┘
        ┌────────────┼──────────────┐
        ▼                           ▼
 LocalStorage (MVP)          GoogleDriveStorage (V2, MCP)
```
Service는 항상 `storage.save(...)`만 부른다. Local이든 Drive든 **부르는 코드는 똑같다.**
→ V2에서 Drive 붙일 때 Service 수정 0.

### 6.2 DB (SQLite → PostgreSQL)
- **SQLAlchemy(ORM)** 로 테이블을 파이썬 클래스로 다룬다 → 특정 SQL 방언에 안 묶임.
- **Alembic**으로 스키마 변경을 마이그레이션 파일로 관리 → PostgreSQL 전환이 설정 변경 수준.
- Repository Layer가 ORM을 감싸므로, Service는 DB 종류를 아예 모른다.

---

## 7. 확장 지점 — "붙일 자리"의 정확한 위치 (P3)

V2 기능이 **정확히 어디에 꽂히는지**를 못박아 둔다.
**V2-1에서 첫 구독자(Notion)가 실제로 붙었다** — `hooks/notion.py`, 상세는 docs/07.

```
프로젝트 생성 ──▶ [HOOK: on_project_created]  ──▶ ✅ (V2-1) Notion 프로젝트 페이지 생성
업로드 완료 ──▶ [HOOK: on_upload_complete]  ──▶ (V2 예정) Notion "데이터 추가됨" 기록
커팅 완료  ──▶ [HOOK: on_processing_done]  ──▶ ✅ (V2-1) Notion 커팅 요약 / (예정) Drive 업로드
CSV 생성  ──▶ [HOOK: on_dataset_exported]  ──▶ (V2 예정) GitHub 커밋(Dataset 버전)

Service 함수들 ──▶ [Tool Interface]  ──▶ (V2) AI Assistant가 도구로 호출
                    예: get_segment_count(project, filter={distance:"20m"})
                        → "20m 데이터 몇 개?" 질의가 이 함수를 부른다

모든 API 라우터 앞 ──▶ [Auth Middleware 자리]  ──▶ (V2) JWT 검증 삽입
```

### 이벤트 훅이란? (초심자용)
"어떤 일이 끝났을 때 알림을 쏘는 우체통"이라고 생각하면 된다.
MVP에서는 우체통만 설치하고 아무도 편지를 안 읽었다.
**V2-1에서 Notion 구독자가 생겨** 우체통에서 편지를 꺼내 Notion에 기록한다(docs/07).
→ **핵심 로직(커팅·저장)은 Notion/Drive의 존재를 전혀 모른다.** 토큰이 없으면 구독자가
등록되지 않을 뿐, 플랫폼은 MVP와 동일하게 완벽히 동작한다.

---

## 8. 기술 스택의 계층별 배치 (요구사항 반영)

| 계층 | 기술 | 이유 |
|---|---|---|
| Frontend | Next.js + React + Tailwind | 요구 스택. 문서 풍부·표준적(R6). Grayish-Blue 미니멀 테마 |
| API | FastAPI | 자동 Swagger 문서(R4), 파이썬 표준, AI/MCP 확장 용이 |
| Service | 순수 파이썬 | 프레임워크 독립 → 테스트/재사용 쉬움 |
| Audio Core | librosa · pydub · soundfile · ffmpeg · numpy · pandas | 요구 스택. 성숙·문서 많음(R7) |
| ORM/DB | SQLAlchemy + Alembic + SQLite→PostgreSQL | 방언 독립·마이그레이션(R3) |
| 비동기 | FastAPI BackgroundTasks (→ V2 Celery) | MVP 단순성, 승격 경로 확보 |
| 패키지관리 | uv (Python) / npm (Front) | 요구 스택 |

---

## 9. 에러·이력 처리 (연구 재현성)

연구 플랫폼이므로 "무엇을 언제 어떻게 처리했나"가 남아야 한다.
- **Upload History**: 누가/언제/무슨 파일을 올렸나.
- **Processing History**: 어떤 전략·파라미터로 커팅했나, 성공/실패, 몇 개 생성.
- 실패한 Job은 status=failed + 에러 메시지 저장 → 대시보드에서 확인·재시도.

> 이유: 연구는 **재현 가능해야** 한다. "이 데이터셋이 어떤 설정으로 만들어졌는지"를
> 추적할 수 있어야 논문·인수인계에서 신뢰가 선다.

---

## 10. 이 아키텍처가 PRD 요구를 만족하는지 자체 점검

| PRD 요구 | 충족 근거 |
|---|---|
| 도메인 독립(G1/R1) | 전략 패턴 + 설정 주도(5장), 데이터 흐름 공통(3장) |
| 저장소 확장(R2) | StorageBackend 인터페이스(6.1) |
| DB 확장(R3) | ORM+Alembic+Repository(6.2) |
| MCP 플러그인(R5) | 이벤트 훅 지점 명시(7장), 핵심로직은 MCP 무지 |
| 유지보수·초심자(R4/R6) | 계층 분리(2장) + Swagger + 표준 패턴 |
| 대용량 처리 | 비동기 Job(4장) |
| 재현성 | 이력 모델(9장) |

---

## 다음 단계
이 구조를 **폴더/파일 배치**로 옮긴다 → **03 폴더구조 설계**.
각 계층(API/Service/Audio Core/Repository/Storage)이 실제 어느 디렉터리에 어떤 파일로 존재하는지,
그리고 Claude Code가 헷갈리지 않게 하는 명명 규칙을 정한다.
