# 12 — 프로젝트 갭 분석 및 개선 설계 (2026-07-13 감사)

> **목적**: 코드·문서·운영 이력 전반을 감사해 부족한 부분을 찾고, 우선순위별 수정 설계를
> 확정한다. 각 항목은 **증거(실제 코드/사고 이력)** 기반이다. 승인된 항목만 구현한다.
> 감사 범위: backend/app 전체, frontend, docs 01~11, git 이력, 실데이터(DB) 운영 경험.

- **버전**: v1.0 (설계 검토용)
- 심각도: **P0** 데이터 손실/서비스 잠김 가능 · **P1** 운영 반복 비용/사고 재발 위험 · **P2** 기능 공백/개선

---

## A. 신뢰성 (P0 — 먼저 고쳐야 함)

### A1. 파일명 충돌 → 조용한 세그먼트 덮어쓰기 (잠재 데이터 손실)

**증거**: `worker.py:101` — seq가 **Job마다 1부터** 시작. `LocalStorage.save`는 존재 확인 없이
덮어씀. `Segment.storage_path`에 유니크 제약 없음.

**사고 시나리오** (경적 프로젝트에서 현실적): 같은 조합을 두 번 녹음(원본 2개)해 각각
커팅하면 — 같은 날짜·같은 라벨 → **같은 파일명 `..._001~030.wav`** → 두 번째 Job이 첫
Job의 wav 30개를 **조용히 덮어쓰고**, DB에는 60개 row가 같은 30개 파일을 가리킨다.
재생·파형·CSV 전부 오염되는데 **아무 에러도 없다.**

**수정 설계**:
1. worker의 seq 시작값 = `segment_repo.count_by_dataset(dataset_id) + 1`
   (Job 단위 → **dataset 누적 단위**로. 실행 당시 시작값을 Job.params에 기록 — 재현성 유지)
2. 이중 안전장치: 저장 직전 `storage.exists(logical_path)`면 Job을 **명시적 실패**
   ("파일명 충돌: {name} — naming_pattern에 구분 필드가 부족합니다")
   → 조용한 덮어쓰기를 구조적으로 금지.
3. 테스트: 같은 dataset에 원본 2개를 별도 Job으로 커팅 → 파일명 연속(031~) + 60개 파일 실존.

### A2. 서버 재시작 시 고아 Job → 커팅 영구 잠김

**증거**: `has_running()` 가드는 `queued/running` Job이 있으면 409를 던지는데, 서버가
Job 실행 중 죽으면(크래시·Ctrl-C) 그 Job이 **영원히 running으로 남는다**. 복구 코드 없음
(main.py에 startup 정리 없음). → 해당 dataset은 재기동 후에도 커팅 요청이 전부 409.

**수정 설계**: `main.py` 기동 시 1회 — `queued/running` 상태의 모든 Job을
`failed`(error_msg="서버 재시작으로 중단됨")로 마킹 + 해당 dataset status를 `collecting`으로
복구. (MVP는 단일 프로세스 BackgroundTasks라 기동 시점에 진행 중 Job이 존재할 수 없음 —
안전한 전제.) 테스트: running Job을 심어놓고 앱 재기동 → failed 전환 확인.

---

## B. 운영 반복 비용 (P1)

### B1. 삭제 API 부재 — 수동 ORM 스크립트 3회 반복

**증거**: 운영 중 세 차례(테스트 프로젝트, 중복 SourceFile, TEST 조합 30개) 삭제를 전부
ORM 스크립트로 수행. "같은 지시 2회 이상 반복 → 승격" 규칙 해당. `@router.delete` 0개.

**수정 설계**: 4개 엔드포인트 + Service (06_API.md 계약 추가):
- `DELETE /api/segments/{id}` — row + 파일 (+미러 삭제 자동)
- `DELETE /api/source-files/{id}` — 참조 세그먼트 있으면 409 (먼저 세그먼트 정리 유도)
- `DELETE /api/datasets/{id}` — cascade + 파일 일괄
- `DELETE /api/projects/{id}` — cascade + 파일 일괄
공통: 실수 방지로 dataset/project 삭제는 `?confirm=<이름>` 쿼리 필수(이름 불일치 400).
프론트: 상세 화면에 삭제 버튼 + 이름 입력 확인 다이얼로그.

### B2. 중복 업로드 무감지 — SourceFile row 중복 (실사고 1회)

**증거**: 같은 파일을 두 번 업로드 → 스토리지는 덮어쓰고 row는 2개 생성(dataset 5에서 발생,
수동 정리함). 이후 전체 재커팅 시 같은 오디오가 두 번 잘릴 뻔.

**수정 설계**: `upload_service._register_one`에서 같은 dataset에 같은 filename의
SourceFile이 있으면 **409** — "이미 존재. 재업로드하려면 기존 원본을 삭제(B1)하거나
파일명을 바꾸세요." (자동 대체는 위험 — 세그먼트가 참조 중일 수 있음.)

### B3. 프론트 재처리 UX 공백 (docs/10 §7 예고 후속)

**증거**: `replace_existing`/`inherit_labels`가 프론트 코드에 전무. 409 메시지 표시만 되고,
UI에서 대체 재커팅을 실행할 방법이 없다.

**수정 설계**: ProcessingPanel — 409 수신 시 안내와 함께 **"기존 세그먼트 대체 (라벨 자동
승계)"** 확인 버튼 → `replace_existing: true`로 재요청. 라벨 승계 끄기 체크박스(기본 켜짐).

---

## C. 데이터 품질 (P1)

### C1. 빈 enum 옵션이 저장됨 — 실데이터 오염 사례 존재

**증거**: `LabelSchemaEditor.tsx:43` — type을 enum으로 바꾸면 기본 options가 `[""]`.
그대로 저장 가능. **project 3의 `valve: enum, options: ['']`가 실제로 이렇게 만들어졌다.**
백엔드 `LabelFieldSchema`도 "options 비어있지 않음"만 검사해 `['']`를 통과시킴.

**수정 설계**: 양쪽 방어 —
- 백엔드: `LabelFieldSchema` validator에 빈 문자열/공백 옵션·중복 옵션 거부 추가.
- 프론트: 저장 전 빈 옵션 필터링 + enum인데 유효 옵션 0개면 저장 버튼 비활성.
- 기존 데이터: project 3 스키마는 사용자와 상의해 수동 수정(자동 마이그레이션 비목표).

### C2. 개별 라벨 수정 UI 미연결

**증거**: `lib/api.ts`에 `updateSegmentLabels`가 있으나 **어느 컴포넌트도 사용하지 않음**.
개별 예외 보정(06 §8)은 현재 curl로만 가능.

**수정 설계**: SegmentTable 라벨 셀 클릭 → 인라인 편집 폼(LabelValuesForm 재사용,
label_schema 기반 자동 생성) → PATCH → 행 갱신. 검증 오류(400)는 셀 옆에 표시.

---

## D. 기능 공백 (P2 — 필요 시점에)

| # | 항목 | 증거/영향 | 수정 방향 |
|---|---|---|---|
| D1 | **event 커팅 전략 미구현** | PRD F3은 event/silence/fixed 3종을 명시 — event만 공백 (`cutting/`에 파일 없음) | onset 기반 전략 1클래스 + registry (P1 패턴 그대로). 실데이터로 튜닝 필요하므로 수요 생길 때 |
| D2 | **mp3/flac/m4a 미검증** | 업로드는 허용(ALLOWED_FORMATS)하나 커팅은 soundfile 의존 — **m4a는 libsndfile 미지원이라 Job 실패 예상**. ffmpeg도 이 머신에 미설치 | 실측 후: 되는 포맷만 ALLOWED_FORMATS에 남기거나, m4a→wav 변환(ffmpeg) 업로드 전처리 추가 |
| D3 | **Notion 단방향 한계** | 프로젝트 이름 변경(PATCH)이 Notion 페이지에 미반영 | `on_project_updated` 훅 + 구독자 (기존 패턴 반복) |
| D4 | **"업로드 진행률" 의미 어긋남** | 집계가 세그먼트 duration 합 — 업로드만 하고 커팅 전이면 0%로 표시됨 | 명칭을 "수집 진행률"로 바꾸거나, SourceFile duration 합으로 집계 변경 (정책 결정 필요) |

## E. 운영·백업 (P2)

| # | 항목 | 현황 | 방향 |
|---|---|---|---|
| E1 | 원본(uploads/)·DB 백업 정책 부재 | docs/09에서 "별도 정책"으로 미룸. 현재 로컬 단일 사본 | 옵션 문서화: `DRIVE_MIRROR_PREFIXES`에 uploads 추가(간단) vs 주기 백업 스크립트. 결정만 하면 됨 |

---

## 이상 없음 확인 (감사했으나 문제 없던 것)

- CUTTING_MODES에 silence_based 등록됨 (CLAUDE §5 규칙 준수)
- 다운로드/미러/재처리 가드/훅 격리/문서 맵 — 최근 마일스톤에서 정비 완료
- 테스트 133개 green, 문서-구현 정합(06↔routes 대조)

---

## 제안 마일스톤

| 마일스톤 | 내용 | 규모 | 상태 |
|---|---|---|---|
| **G-M1 (P0)** | A1 파일명 충돌(누적 seq + exists 가드) + A2 고아 Job 복구 + 테스트 | 소 | ✅ 2026-07-13 실서버 시나리오 검증 (같은 조합 2회 녹음 → 파일명 연속 4개·중복 0 / 고아 Job 재시작 복구 → 202) |
| **G-M2 (P1 백엔드, 부분)** | B1 삭제 API 4종 + B2 중복 업로드 409 + C1 빈 enum 방어(백+프론트) + 06 계약 갱신 | 중 | ✅ 2026-07-13 실서버 검증 (409/422/204 전부 확인). **B3·C2는 보류** (수집 후 논의) |
| **G-M3 (P1 프론트)** | B3 대체 재커팅 버튼 + C2 라벨 인라인 편집 + 삭제 버튼(B1 UI) + 브라우저 검증 | 중 | ✅ 2026-07-13 실서버 브라우저 검증 9/9 통과 (수집 전으로 앞당김 — 사용자 결정) |
| **G-M4 (P2)** | D1~D4·E1 중 승인 항목만 | 항목별 | ⏸ 보류 |

**비목표**: 라벨 이력 버저닝, 자동 스키마 마이그레이션, Celery 승격, 인증(별도 마일스톤).
