# CLAUDE.md

> Claude Code가 매 세션 자동으로 읽는 **규칙 파일**. 이 프로젝트에서 코드를 짜거나 수정할 때
> 아래 규칙을 **항상** 지킨다. 상세 배경은 `docs/01_PRD.md`, `docs/02_architecture.md`,
> `docs/03_structure.md` 참조. 규칙과 지시가 충돌하면 사용자에게 먼저 확인한다.

---

## 1. 이 프로젝트가 무엇인가 (한 문단)

대학 연구실용 **오디오 데이터셋 관리 플랫폼**. 오디오 수집→전처리→자동 커팅→메타데이터→데이터셋→
연구기록을 자동화한다. **차량음·심음·산업음·음성 등 어떤 오디오 도메인에도 재사용**되어야 한다.
특정 도메인(예: 차량 경적)에 종속된 코드를 짜면 안 된다.

## 2. 절대 원칙 (위반 금지)

- **P1. 도메인은 설정에 둔다.** 커팅 방식·파일명 규칙·라벨은 **Project 설정**에서 온다.
  코드에 `if project == "차량음"` 같은 **도메인 분기문을 절대 넣지 않는다.**
- **P2. 의존 방향은 한 방향.** `api → services → (audio / repositories / storage)`.
  `audio/`는 web·DB를 **import 하지 않는다** (순수 파이썬 + 오디오 라이브러리만).
- **P3. 부품은 인터페이스 뒤에.** 저장소는 `StorageBackend`, DB는 Repository/ORM 뒤에 둔다.
  Service는 SQLite인지 Local인지 **몰라야** 한다.
- **P4. V2는 지금 만들지 않는다. 자리만 만든다.** MCP·AI·Auth가 없어도 완전히 동작해야 한다.
  이들은 `hooks/`·인터페이스를 통해 나중에 플러그인처럼 붙는다.

## 3. 기술 스택 (고정 — 임의 변경 금지)

- Backend: **Python 3.12+ / FastAPI**, 패키지 관리 **uv**
- ORM/DB: **SQLAlchemy + Alembic**, MVP는 **SQLite** (PostgreSQL 전환은 DB URL만 교체)
- Audio: **librosa · pydub · soundfile · ffmpeg · numpy · pandas**
- Frontend: **Next.js(App Router) + React + Tailwind**, 패키지 관리 **npm**
- 비동기: MVP는 **FastAPI BackgroundTasks** (Celery/Redis는 V2까지 도입 금지)
- 새 라이브러리 추가가 필요하면 **먼저 사용자에게 이유와 함께 제안**하고 승인받는다.

## 4. 폴더 배치 규칙 (`docs/03_structure.md`와 일치)

| 무엇을 짜나 | 어디에 두나 |
|---|---|
| HTTP 엔드포인트 | `backend/app/api/routes/` |
| 업무 흐름(오케스트레이션) | `backend/app/services/` |
| 오디오 처리(순수 로직) | `backend/app/audio/` |
| **새 커팅 방식** | `backend/app/audio/cutting/` (파일 추가 + registry 등록만) |
| DB 접근 | `backend/app/repositories/` |
| DB 테이블(ORM) | `backend/app/models/` |
| API 입출력 형태(Pydantic) | `backend/app/schemas/` |
| 저장소 구현 | `backend/app/storage/` |
| 확장 훅 | `backend/app/hooks/` |
| **외부 서비스 구독자(V2)** | `backend/app/hooks/` (예: `notion.py` — 토큰 없으면 no-op, docs/07) |
| 프론트 백엔드 호출 | `frontend/lib/api.ts` (컴포넌트가 직접 fetch 금지) |

- **models(ORM)와 schemas(Pydantic)를 절대 한 파일에 섞지 않는다.**
- 프론트 색상은 `tailwind.config.ts` 토큰만 사용. 컴포넌트에 색 하드코딩 금지.

## 5. 코딩 컨벤션

- Python: PEP8, **타입 힌트 필수**, 함수/변수 명확한 영어 이름.
- 각 함수는 한 가지 일만. Service가 흐름을 조립하고, 실제 처리는 audio/repository로 위임.
- API 응답·요청은 반드시 **Pydantic schema**로 검증. 원시 dict 반환 금지.
- 모든 라우터는 **자동 문서(Swagger)에 뜨도록** summary/response_model 지정.
- 하드코딩 경로 금지. 경로·설정은 `core/config.py`(.env)에서 읽는다.
- 오디오 파일 접근은 **항상 Storage 인터페이스 경유** (직접 `open()` 금지).

## 6. 데이터 모델 핵심 (상세는 05 문서)

3층: **Project → Dataset → Segment**.
- Project: 도메인 설정(cutting_mode, naming_pattern, label_schema)을 가진다.
- Dataset: Project 내부의 버전 있는 묶음.
- Segment: 커팅된 조각 1개 = 메타데이터 1행. 자동메타 + 라벨.
- History(Upload/Processing)와 Job으로 **재현성**을 남긴다.

## 7. 작업 방식 (Claude Code 행동 규칙)

- **큰 기능은 한 번에 다 짜지 말고** 계층 단위로 나눠 제안 후 진행한다.
- 새 파일·구조를 만들기 전에 `docs/03_structure.md`의 배치와 맞는지 확인한다.
- 애매하면 **추측하지 말고 질문**한다 (특히 데이터 모델·API 계약).
- 커팅/네이밍 로직은 `tests/`에 **테스트를 함께** 작성한다 (audio/는 독립 테스트 가능).
- 기존 규칙을 어기게 되는 상황이면, 코드를 짜기 전에 그 사실을 먼저 알린다.

## 8. 하지 말 것 (Don'ts)

- 도메인 분기문(`if 차량음`) 넣기.
- `audio/`에서 FastAPI·SQLAlchemy import 하기.
- Service에서 SQL 직접 쓰기(반드시 Repository 경유).
- MVP에 로그인/인증·Celery·클라우드 배포 코드 넣기.
- 커팅을 HTTP 요청 안에서 동기 실행하기(반드시 백그라운드 Job).
- 승인 없이 스택·주요 구조 바꾸기.

## 9. 현재 진행 상황

> **업데이트 규칙**: 마일스톤(M, V2-N, D-MN 등)이 하나 끝나고 커밋할 때마다,
> 이 섹션을 그 시점 상태로 업데이트한다(완료 항목·진행 중 항목·최신 커밋 해시).
> 세션·계정·컴퓨터가 바뀌어도 이 섹션만 읽으면 현재 위치를 알 수 있게 유지한다.

- ✅ **MVP (M1~M10)** 완료, 도메인 재사용성 검증 통과 — 커밋 `bdcbd12`
- ✅ **V2-1**: Notion 연동 완료 (프로젝트 생성 → DB row, 커팅 완료 → 요약 기록) — `6aef08b`
- ✅ **V2-1b**: Notion 연구노트 확장 완료 (자동기록/수기노트 섹션 분리, cutting_params 기록) — `3335036`
- ✅ **V2-2**: silence_based 커팅 전략 완료 (+ 튜닝 가이드 docs/08) — `1a840f0`
- 🔄 **V2-3**: Google Drive CSV 미러링 — **D-M4까지 완료** — `8496ebd`
  (설정 분기·DriveStorage·MirrorStorage·setup 스크립트. 남은 것: D-M5 실연동
  — 사용자 GCP 설정 필요, D-M6 문서 마무리. 계획: docs/09 §7)
- **최신 마일스톤 커밋**: `8496ebd` (V2-3 D-M4)
- 남은 V2 자리: GitHub(Dataset 버전), AI Assistant, Auth.

V2에서도 위 원칙(P1~P4)과 금지사항은 그대로 유효하다. 외부 서비스 구독자는
반드시 hooks/에 두고, 실패가 본 흐름을 깨지 않게 한다.
