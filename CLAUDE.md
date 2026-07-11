# CLAUDE.md

> Claude Code가 매 세션 자동으로 읽는 **규칙 파일**. 이 프로젝트에서 코드를 짜거나 수정할 때
> 아래 규칙을 **항상** 지킨다. 규칙과 사용자 지시가 충돌하면 사용자에게 먼저 확인한다.
> 상세 배경은 §4 문서 맵에서 해당 문서를 찾아 읽는다.

---

## 0. 세션 시작 시 (오리엔테이션)

새 세션에서 작업을 시작하기 전에, 순서대로:
1. **§11 현재 진행 상황**을 읽는다 — 어디까지 됐고 지금 뭘 하는 중인지.
2. 진행 중 마일스톤이 있으면 **해당 설계 문서**(§11에 표기, 예: docs/09)를 읽는다.
3. `git log --oneline -5`로 §11과 실제 이력이 일치하는지 확인한다. 어긋나면 사용자에게 알린다.

## 1. 이 프로젝트가 무엇인가 (한 문단)

대학 연구실용 **오디오 데이터셋 관리 플랫폼**. 오디오 수집→전처리→자동 커팅→메타데이터→데이터셋→
연구기록을 자동화한다. **차량음·심음·산업음·음성 등 어떤 오디오 도메인에도 재사용**되어야 한다.
특정 도메인(예: 차량 경적)에 종속된 코드를 짜면 안 된다. MVP는 완료됐고 현재 V2(외부 연동)를
플러그인 방식으로 붙여가는 중이다(§11).

## 2. 절대 원칙 (하드 룰 — 위반 금지)

- **P1. 도메인은 설정에 둔다.** 커팅 방식·파일명 규칙·라벨은 **Project 설정**에서 온다.
  코드에 `if project == "차량음"` 같은 **도메인 분기문을 절대 넣지 않는다.**
- **P2. 의존 방향은 한 방향.** `api → services → (audio / repositories / storage)`.
  `audio/`는 web·DB를 **import 하지 않는다** (순수 파이썬 + 오디오 라이브러리만).
- **P3. 부품은 인터페이스 뒤에.** 저장소는 `StorageBackend`, DB는 Repository/ORM 뒤에 둔다.
  Service는 SQLite인지 Local인지 Drive인지 **몰라야** 한다.
- **P4. 외부 연동은 플러그인이다.** Notion·Drive 등 외부 서비스는 `hooks/` 구독자 또는
  Storage 구현체로만 붙는다. **토큰/설정이 없으면 등록되지 않을 뿐, 코어는 100% 동일하게
  동작해야 한다.** 구독자 실패는 로그만 남기고 본 흐름을 절대 깨지 않는다.
  (실증: `hooks/notion.py`, `storage/drive.py` — 이 패턴을 그대로 따른다.)

## 3. 기술 스택 (고정 — 임의 변경 금지)

- Backend: **Python 3.12+ / FastAPI**, 패키지 관리 **uv** (`uv run ...`으로 실행)
- ORM/DB: **SQLAlchemy + Alembic**, DB는 **SQLite** (PostgreSQL 전환은 DB URL만 교체)
- Audio: **librosa · pydub · soundfile · ffmpeg · numpy · pandas**
- Frontend: **Next.js(App Router) + React + Tailwind**, 패키지 관리 **npm**
- 비동기 작업: **FastAPI BackgroundTasks** (Celery/Redis 도입은 사용자 승인 필요)
- 새 라이브러리 추가가 필요하면 **먼저 사용자에게 이유와 함께 제안**하고 승인받는다.

## 4. 문서 맵 (docs/ — 04는 의도적 결번, 새 문서에 재사용하지 않는다)

| 문서 | 내용 | 언제 읽나 |
|---|---|---|
| 01_PRD.md | 목적·기능 요구·V2 로드맵 | 기능의 "왜"가 필요할 때 |
| 02_architecture.md | 계층 구조·훅·설계 결정 | 구조 변경 전 |
| 03_structure.md | 폴더 트리 정본 | 새 파일 만들기 전 |
| 05_database.md | 데이터 모델 상세 | 모델/마이그레이션 작업 전 |
| 06_API.md | **API 계약 정본** (엔드포인트·schema·Job 흐름) | API 추가·변경 전 (변경 시 함께 갱신) |
| 07_notion_integration.md | V2-1 Notion 연동 설계 | Notion 훅 작업 시 |
| 08_cutting_tuning.md | silence_based 튜닝 가이드 | 커팅 품질 문제 시 |
| 09_drive_integration.md | V2-3 Drive 미러링 설계·마일스톤 | Drive 작업 시 |

큰 기능은 이 패턴을 따른다: **설계 문서(docs/0N)를 먼저 쓰고 사용자 승인 → 문서대로 구현**
(06→MVP, 07→V2-1, 09→V2-3 전부 이렇게 진행됨).

## 5. 폴더 배치 규칙 (`docs/03_structure.md`와 일치)

| 무엇을 짜나 | 어디에 두나 |
|---|---|
| HTTP 엔드포인트 | `backend/app/api/routes/` |
| 업무 흐름(오케스트레이션) | `backend/app/services/` |
| 백그라운드 Job 실행 | `backend/app/background/worker.py` |
| 오디오 처리(순수 로직) | `backend/app/audio/` |
| **새 커팅 방식** | `backend/app/audio/cutting/` 파일 추가 + `__init__.py` import 한 줄(registry 등록) **+ 프론트 `CuttingConfigFields.tsx`의 `CUTTING_MODES`에 항목 추가** |
| DB 접근 | `backend/app/repositories/` |
| DB 테이블(ORM) | `backend/app/models/` |
| API 입출력 형태(Pydantic) | `backend/app/schemas/` |
| 저장소 구현 | `backend/app/storage/` (예: `local.py`·`drive.py`·`mirror.py`) |
| 외부 서비스 구독자 | `backend/app/hooks/` (예: `notion.py` — 토큰 없으면 no-op) |
| 백엔드 운영 스크립트 | `backend/scripts/` (예: `setup_drive_auth.py`) |
| 프론트 백엔드 호출 | `frontend/lib/api.ts` — **컴포넌트가 직접 fetch 금지**, `request()` 헬퍼 사용 |
| 프론트 UI 조각 | `frontend/components/<영역>/` (ui·layout·dashboard·projects·datasets·upload) |
| 개발 편의 스크립트 | `scripts/` (예: `dev.sh`) |

- **models(ORM)와 schemas(Pydantic)를 절대 한 파일에 섞지 않는다.**
- 프론트 색상은 `tailwind.config.ts` 토큰만 사용. 컴포넌트에 색 하드코딩 금지.

## 6. 코딩 컨벤션

- Python: PEP8, **타입 힌트 필수**, 함수/변수 명확한 영어 이름. 주석·docstring은 한국어.
- 각 함수는 한 가지 일만. Service가 흐름을 조립하고, 실제 처리는 audio/repository로 위임.
- API 응답·요청은 반드시 **Pydantic schema**로 검증. 원시 dict 반환 금지.
- 모든 라우터는 **자동 문서(Swagger)에 뜨도록** summary/response_model 지정.
- 하드코딩 경로 금지. 경로·설정은 `core/config.py`(.env)에서 읽는다.
- 오디오 파일 접근은 **항상 Storage 인터페이스 경유** (직접 `open()` 금지).

## 7. 데이터 모델 핵심 (상세는 docs/05)

3층: **Project → Dataset → Segment**.
- Project: 도메인 설정(cutting_mode, cutting_params, naming_pattern, label_schema)을 가진다.
- Dataset: Project 내부의 버전 있는 묶음.
- Segment: 커팅된 조각 1개 = 메타데이터 1행. 자동메타 + 라벨.
- History(Upload/Processing)와 Job으로 **재현성**을 남긴다.

## 8. 실행·검증 방법

```bash
./scripts/dev.sh                      # 개발 서버 한 번에: backend :8000 + frontend :3000
                                      # 둘 다 저장 시 자동 반영, Ctrl-C 한 번에 종료
cd backend && uv run pytest -q        # 백엔드 전체 테스트
cd frontend && npm run build          # 프론트 타입체크 + 빌드
```

- `frontend/.env.local`이 없으면 dev.sh가 `.env.local.example`에서 자동 생성한다.
- **함정**: dev 서버가 켜진 상태에서 `npm run build` 금지 — `.next`가 깨져 간헐적 500
  (`Cannot find module './NNN.js'`)이 난다. 깨졌으면 서버 끄고 `rm -rf frontend/.next`.
- **브라우저 검증**: `.claude/skills/run-audio-platform/` 스킬 사용.
  `node driver.mjs smoke`가 골든 패스(프로젝트 생성→업로드→커팅→export→대시보드)를
  격리 환경에서 자동 검증하고 스크린샷을 남긴다. 세부 명령은 그 SKILL.md 참조.

## 9. 작업 방식 (Claude Code 행동 규칙)

- **큰 기능은 한 번에 다 짜지 말고** 계층 단위로 나눠 제안 후 진행한다.
  더 큰 단위(외부 연동 등)는 설계 문서부터(§4 패턴).
- 새 파일·구조를 만들기 전에 `docs/03_structure.md`의 배치와 맞는지 확인한다.
- 애매하면 **추측하지 말고 질문**한다 (특히 데이터 모델·API 계약).
- 커팅/네이밍 로직은 `tests/`에 **테스트를 함께** 작성한다 (audio/는 독립 테스트 가능).
- UI를 바꿨으면 **실제 브라우저로 확인**(스크린샷)한 뒤에 완료라고 보고한다.
  SSR 응답 확인만으로 "된다"고 하지 않는다.
- 기존 규칙을 어기게 되는 상황이면, 코드를 짜기 전에 그 사실을 먼저 알린다.
- **커밋 메시지 형식 (하드 룰)**: 한국어로 쓴다. 마일스톤 커밋은
  `V2-3(D-M1~M4): 요약` 형식의 접두사를 붙인다. 커밋은 저장소 **루트에서** 실행한다.
- 프론트 자동 테스트 프레임워크는 **도입하지 않기로 결정**(사용자 확정).
  프론트 검증은 `npm run build` + 실제 브라우저 확인이 공식 방식이다.

## 10. 완료의 정의 (Definition of Done)

작업을 "완료"라고 보고하기 전에 전부 체크:

1. `cd backend && uv run pytest -q` **전부 통과** (백엔드를 건드렸다면).
2. `cd frontend && npm run build` **통과** (프론트를 건드렸다면 — dev 서버 끄고).
3. UI 변경이면 **브라우저에서 실제 동작 확인** (§8 스킬, 스크린샷).
4. API·데이터 모델 계약이 바뀌었으면 **docs/06(및 해당 설계 문서) 갱신**.
5. 새 함정·비직관적 동작을 발견했으면 해당 문서(스킬 Gotchas 등)에 기록.
6. 마일스톤 완료 커밋이면 **§11을 그 시점 상태로 갱신**.

## 11. 현재 진행 상황

> **업데이트 규칙 (하드 룰)**: 마일스톤(M, V2-N, D-MN 등)이 하나 끝나고 커밋할 때마다,
> 이 섹션을 그 시점 상태로 업데이트한다(완료 항목·진행 중 항목·최신 커밋 해시).
> 세션·계정·컴퓨터가 바뀌어도 이 섹션만 읽으면 현재 위치를 알 수 있게 유지한다.

- ✅ **MVP (M1~M10)** 완료, 도메인 재사용성 검증 통과 — 커밋 `bdcbd12`
- ✅ **V2-1**: Notion 연동 완료 (프로젝트 생성 → DB row, 커팅 완료 → 요약 기록) — `6aef08b`
- ✅ **V2-1b**: Notion 연구노트 확장 완료 (자동기록/수기노트 섹션 분리, cutting_params 기록) — `3335036`
- ✅ **V2-2**: silence_based 커팅 전략 완료 (+ 튜닝 가이드 docs/08) — `1a840f0`
- 🔄 **V2-3**: Google Drive CSV 미러링 — **D-M1~D-M4 완료** — `8496ebd`
  (설정 분기·DriveStorage·MirrorStorage·setup 스크립트 완료.
  **D-M5 실연동은 사용자 GCP 설정 대기 중**, 이후 D-M6 문서 마무리. 계획: docs/09 §7)
- **최신 마일스톤 커밋**: `8496ebd` (V2-3 D-M4)
- 남은 V2 자리: GitHub(Dataset 버전), AI Assistant, Auth.

## 12. 하지 말 것 (Don'ts)

- 도메인 분기문(`if 차량음`) 넣기.
- `audio/`에서 FastAPI·SQLAlchemy import 하기.
- Service에서 SQL 직접 쓰기(반드시 Repository 경유).
- 로그인/인증·Celery·클라우드 배포 코드 넣기 (아직 승인된 마일스톤 아님).
- 커팅을 HTTP 요청 안에서 동기 실행하기(반드시 백그라운드 Job).
- 외부 연동 실패가 업로드·커팅·export 본 흐름을 깨게 만들기 (P4).
- 승인 없이 스택·주요 구조 바꾸기.

## 13. 작업 품질 기준 (모델 무관 — 어떤 모델이 와도 지킨다)

- **검증 없이 "된다"고 말하지 않는다.** 코드를 고쳤으면 실행해서 확인한 뒤에
  완료라고 보고한다. 실행 못 했으면 "실행은 못 해봤다"고 명시한다.
- **버그는 재현부터.** 수정 전에 문제를 재현하는 스크립트/테스트를 만들고,
  수정 후 **같은 방법으로** 사라졌는지 확인한다. 재현 없이 고치지 않는다.
- **증상이 아니라 원인을 고친다.** 워크어라운드로 덮게 되면 그 사실과 근본
  원인을 함께 기록한다. 과거에 "환경 탓"으로 기록된 것이 앱 버그였던 사례가
  있다 — 기존 문서의 원인 설명도 의심할 수 있다.
- **작업 중 이상 신호를 그냥 지나치지 않는다.** 기대값과 화면·로그가 다르면
  (예: 1.1초가 1.0초로 표시) 본 작업과 무관해 보여도 원인을 확인하고 보고한다.
- **발견한 함정은 그 자리에서 문서화한다.** 스킬 Gotchas, docs/08 같은
  지식 문서에 남긴다. 다음 세션의 나는 기억하지 못한다.
- **같은 지시를 두 번 이상 반복받으면** 스킬(.claude/skills/)이나 규칙(이 파일)로
  승격을 제안한다.
- **보고는 결론 먼저.** 테스트 실패는 실패라고, 건너뛴 건 건너뛰었다고 쓴다.
- **모호하면 질문하고, 사용자가 말한 적 없는 선호를 지어내지 않는다.**
