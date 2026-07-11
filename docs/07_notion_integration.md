# 07 — Notion 연동 설계 (V2-1: 프로젝트 페이지 + 커팅 요약)

> **목적**: MVP 때 설치해 둔 이벤트 훅에 **첫 번째 구독자(Notion)**를 붙이는 V2-1의 계약을 확정한다.
> 06_API.md처럼 이 문서가 승인되면 그대로 구현한다.
> 연결: 01_PRD.md §6(V2 표) · 02_architecture.md §7(훅 위치) → (이 문서)

- **버전**: v1.0
- **원칙(P4)**: Notion은 **플러그인**이다. 토큰이 없으면 구독자가 등록되지 않을 뿐,
  플랫폼은 MVP와 100% 동일하게 동작한다. 핵심 로직(services/audio/worker)은 Notion의 존재를 모른다.

---

## 1. 목표와 범위

### 하는 것
1. **프로젝트 생성 시** → Notion "프로젝트" 데이터베이스에 해당 프로젝트 row(=페이지) 자동 생성.
2. **커팅(processing) 완료 시** → 그 프로젝트의 Notion 페이지 **본문에 요약 블록 추가**:
   `"{완료시각} — 세그먼트 {N}개, 총 {M}초 (dataset: {이름}, Job #{id})"`
   → 커팅할 때마다 한 줄씩 쌓여 페이지가 곧 **처리 이력 연구일지**가 된다.

### 안 하는 것 (비목표 — 후속 단계)
- 업로드/CSV export 이벤트 기록 (`on_upload_complete`·`on_dataset_exported` 구독은 다음 단계).
- Notion → 플랫폼 방향 동기화(양방향 아님. 단방향 기록 전용).
- 실패 재시도 큐·전송 보장. 기록 실패는 **로그만 남기고 유실 허용** (연구 로그이지 원본 데이터가 아님).
- 회의록·위키 자동화 (PRD §6의 장기 비전, 이번 범위 아님).

### 왜 REST API인가 (문서의 "MCP" 표기에 대해)
01/02 문서의 "Notion (MCP)"는 "외부 서비스 연동 계층"이라는 의미로 쓰였다. MCP는 AI 클라이언트용
프로토콜이라 FastAPI 백엔드의 런타임 자동화에는 부적합하다. 표준적이고 문서가 풍부한(R6/R7)
**Notion 공식 REST API**(integration 토큰)를 백엔드가 직접 호출한다.
Claude Code의 Notion MCP 도구는 개발 단계에서 **DB 생성·기록 검증**에만 사용한다.

---

## 2. 아키텍처 — 훅 구독 (P4 플러그인)

```
[project_service.create]  commit 후 ──▶ on_project_created.emit(project_id)   ★ 훅 신설
[worker.run_cutting_job]  commit 후 ──▶ on_processing_done.emit(dataset_id, job_id)  (기존)
                                              │
                              (토큰 설정 시에만 구독자 등록)
                                              ▼
                                   hooks/notion.py 구독자
                                   ├─ 데몬 스레드로 분리(비차단)
                                   ├─ 자체 DB 세션으로 상세 조회
                                   └─ Notion REST API 호출 (timeout, 실패=로그만)
```

- **훅 신설**: `on_project_created`. 기존 `Hook` 클래스 그대로 사용, `project_service.create()`의
  commit 이후 `emit(project_id=...)` 한 줄 추가 (upload_service의 기존 emit 패턴과 동일).
- **제거 시 영향 0**: `hooks/notion.py`를 지우고 main.py의 등록 2줄을 빼면 MVP 상태로 복귀.
- **의존 방향 준수(P2)**: notion.py는 hooks/에 있고 repositories·core만 import한다.
  services/audio/worker는 notion.py를 import하지 않는다.

---

## 3. 설정 (backend/.env — core/config.py 경유)

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `NOTION_API_KEY` | str | `""` | integration 토큰 (`ntn_...` 또는 `secret_...`) |
| `NOTION_DATABASE_ID` | str | `""` | "프로젝트" DB의 32자리 hex id |
| `NOTION_API_VERSION` | str | `"2022-06-28"` | Notion-Version 헤더 |
| `NOTION_TIMEOUT_SEC` | float | `10.0` | HTTP 타임아웃 (스레드가 매달리지 않게) |

- **활성화 조건**: `notion_enabled` property = `NOTION_API_KEY`와 `NOTION_DATABASE_ID` **둘 다** 존재.
- 미설정 시: `register_notion_subscribers()`가 no-op → 구독자 0명 → MVP와 동일 동작.
- 판단 시점은 앱 기동 1회. .env 변경은 서버 재기동으로 반영.

---

## 4. Notion "프로젝트" DB 스키마

DB 이름: **"Audio Platform 프로젝트"** (1 row = 플랫폼 Project 1개)

| 속성 이름 | Notion 타입 | 값 (플랫폼 출처) |
|---|---|---|
| 프로젝트명 | title | `Project.name` |
| platform_id | number | `Project.id` — **매핑 키** (아래 §5) |
| 도메인 | select | `Project.domain` (예: vehicle / heart) |
| 커팅 모드 | select | `Project.cutting_mode` |
| 파일명 규칙 | rich_text | `Project.naming_pattern` |
| 목표 시간(초) | number | `Project.target_duration_sec` (null이면 생략) |
| 생성일 | date | `Project.created_at` (UTC ISO8601) |

### 생성·연결 절차 (실연동 단계)
1. 사용자: [notion.so/my-integrations](https://www.notion.so/my-integrations)에서 **내부 integration 생성** → 토큰 발급 → `backend/.env`의 `NOTION_API_KEY`에 기록.
2. Claude Code가 Notion MCP로 위 스키마의 DB를 생성 → URL에서 database_id 추출 → `.env`의 `NOTION_DATABASE_ID`에 기록.
3. **[필수·놓치기 쉬움]** 사용자: 생성된 DB 페이지 우상단 `⋯ → 연결(Connections)`에서 **1번의 integration을 연결**. 이걸 안 하면 토큰이 유효해도 404가 난다.

---

## 5. 이벤트 매핑 (동작 계약)

### 5.0 페이지 본문 구조 (V2-1b — 자동 기록과 수기 노트의 분리)
프로젝트 페이지 본문은 두 섹션으로 나뉜다. 자동 로그는 **컨테이너 안에만** 쌓이고,
연구 노트 영역은 플랫폼이 **절대 건드리지 않는다**.

```
[프로젝트 페이지]
├─ 🤖 자동 기록 (플랫폼)      ← 토글 헤딩(heading_2, is_toggleable) = 로그 컨테이너
│   ├─ • {완료시각} — 세그먼트 N개, 총 M초 (dataset: 이름, Job #id)
│   │     └ {cutting_mode} · {key}={value}, ...   ← 이번 Job의 실제 사용 파라미터
│   └─ • (다음 로그 누적...)
├─ 📝 연구 노트               ← 일반 헤딩 + 빈 문단. 사람 전용 자유 기록 영역
```

- 두 섹션은 **페이지 생성 시 함께 생성**된다(`POST /v1/pages`의 `children`).
- 파라미터 줄은 bullet의 **중첩 자식 문단**. 키를 하드코딩하지 않고
  `Job.params["cutting_params"]` dict를 범용 렌더링한다(P1 — 어떤 전략이 와도 코드 불변).
  `params_override`로 돌린 실험도 Job.params에 실제 사용값이 있으므로 정확히 남는다.

### 5.1 프로젝트 생성 → 페이지 생성
- 구독: `on_project_created(project_id)`
- 동작: 자체 DB 세션으로 Project 조회 → `POST /v1/pages` (parent=database_id, §4 속성,
  children=§5.0의 두 섹션) 1회.

### 5.2 커팅 완료 → 요약 블록 append (컨테이너 안에)
- 구독: `on_processing_done(dataset_id, job_id)` — payload에 project_id가 없으므로
  `dataset.project` relationship으로 역조회.
- 동작:
  1. 자체 세션으로 Job·Dataset·Project 조회, 해당 커팅의 세그먼트 총 길이 합산.
  2. `POST /v1/databases/{id}/query` — `platform_id == project.id` 필터로 페이지 검색.
  3. **페이지 없으면 그 자리에서 생성**(§5.1과 동일 호출) — 연동 이전에 만들어진 기존
     프로젝트도 첫 커팅 때 자동으로 소급 등록된다.
  4. `GET /v1/blocks/{page_id}/children`으로 "자동 기록" 토글 헤딩(컨테이너)을 찾는다.
     **없으면 두 섹션을 페이지 끝에 생성**(구버전 페이지 소급 — 기존 본문은 그대로 둠).
  5. `PATCH /v1/blocks/{컨테이너_id}/children` — bullet + 중첩 파라미터 줄 append:
     ```
     • 2026-07-11 14:40 UTC — 세그먼트 33개, 총 12.0초 (dataset: v1 초기수집, Job #12)
         silence_based · silence_threshold_db=-35, min_silence_sec=0.15, min_segment_sec=0.1
     ```

### 매핑 방식의 근거 (platform_id 조회 채택)
- 플랫폼 DB에 `notion_page_id` 컬럼을 두는 대안은 Alembic 마이그레이션이 필요하고
  코어 모델에 Notion 전용 필드가 들어가 P4가 약해진다.
- Notion 속성 조회는 플랫폼 변경 0, 페이지 재생성에도 자가 복구되며, 이벤트 빈도(연구실 수동
  작업)에서 조회 1회 비용은 무시 가능.

---

## 6. 동작 방식 (비차단·격리)

- **데몬 스레드**: 구독자는 받은 payload를 `threading.Thread(daemon=True)`로 넘기고 즉시 반환.
  → 프로젝트 생성 API 응답이 Notion 지연(수백ms~수초)에 물리지 않는다.
  (asyncio·ThreadPool·Celery는 이 규모에 과설계 — R6, CLAUDE.md §3)
- **자체 DB 세션**: 스레드는 worker.py 패턴 그대로 `SessionLocal()`을 열고 finally에서 닫는다.
  emit이 모두 commit 이후라 최신 상태가 보인다.
- **실패 처리**: HTTP 오류·타임아웃·조회 실패는 `logger.exception`으로 남기고 끝.
  본 흐름(업로드·커팅)은 **절대** 깨지지 않는다. daemon 스레드라 서버 종료 시 진행 중이던
  기록은 유실될 수 있다(허용 — §1 비목표).
- **Notion API 상세**: base `https://api.notion.com`, 헤더 `Authorization: Bearer {key}`,
  `Notion-Version: {version}`, `Content-Type: application/json`.

---

## 7. 테스트 방법

- **신규 `tests/test_notion_hook.py`** (새 테스트 의존성 0):
  - `NotionClient(transport=httpx.MockTransport(handler))` 주입으로 실제 HTTP 없이
    요청 URL·헤더·properties/블록 JSON을 캡처·검증.
  - `_spawn`을 동기 실행으로 몽키패치 → 스레드 타이밍 플레이크 제거.
  - `SessionLocal`·클라이언트 팩토리를 conftest의 worker 패치 패턴대로 교체.
  - 등록 로직: 토큰 없음 → False·구독 0 / 있음 → True·훅 2개에 구독 1씩.
  - lazy 생성 경로: query가 빈 결과 → 페이지 생성 후 append까지 이어지는지.
- **기존 테스트 보호**: conftest에 autouse 픽스처로 매 테스트 전 구독자를 비우고 종료 시 복원
  (`Hook.clear()` 신설) → 개발자 .env에 토큰이 있어도 기존 65+ 테스트는 구독자 0명으로 실행.
- **실연동 검증**: 서버 실기동 → 프로젝트 생성·커팅 실행 → Claude가 Notion MCP `notion-fetch`로
  row·블록 생성을 직접 확인.

---

## 8. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| 401 Unauthorized | 토큰 오타·만료 | `.env`의 `NOTION_API_KEY` 재확인 |
| 404 object_not_found | **integration이 DB 페이지에 연결 안 됨** | §4 절차 3 — DB 페이지 `⋯ → 연결`에서 integration 추가 |
| 400 validation_error | DB 속성 이름/타입 불일치 | §4 스키마와 Notion DB 속성 대조 |
| 기록이 안 남는데 에러도 없음 | `notion_enabled=False` (키 누락) | `.env` 두 키 모두 설정 후 재기동 |
| 서버 로그에 timeout | Notion 응답 지연 | `NOTION_TIMEOUT_SEC` 상향 (기본 10초) |
| "자동 기록" 섹션이 하나 더 생김 | 사용자가 토글 헤딩 제목을 변경/삭제 | 컨테이너는 제목 텍스트("자동 기록")로 찾는다 — 제목을 되돌리거나 새 섹션에 계속 쌓이게 두면 됨 (기록 유실 없음) |

---

## 다음 단계
이 문서 승인 → V2-M1(httpx 승격·설정)부터 계획 순서대로 구현.
후속 단계에서 `on_upload_complete`·`on_dataset_exported` 구독자를 같은 모듈에 추가하면
업로드/CSV 기록도 페이지에 쌓인다(구조 변경 없음).
