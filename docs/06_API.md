# 06 — API 설계 (REST API Contract)

> **목적**: `backend/app/api/routes/`가 노출할 **엔드포인트와 요청/응답 계약(Pydantic schema)**을 확정한다.
> CLAUDE.md는 "API 계약은 추측하지 말고 먼저 정한다"고 요구한다 — 이 문서가 그 계약이다.
> 연결: 02_architecture.md(계층·데이터흐름), 03_structure.md(라우트 파일), 05_database.md(테이블) → (이 문서)

- **버전**: v1.0 (MVP)
- **Base URL**: `/api` (예: `POST /api/uploads`)
- **형식**: 요청·응답 모두 JSON (업로드만 `multipart/form-data`). 모든 응답은 **Pydantic schema로 검증**(원시 dict 금지).
- **문서화**: 모든 라우트는 `summary` + `response_model` 지정 → Swagger(`/docs`)에 자동 노출.

---

## 0. 설계 원칙 (이 문서의 근거)

1. **얇은 API 계층**: 라우트는 검증·직렬화만 하고 흐름은 Service에 위임(02 §2). 같은 Service를 V2에서 AI가 재사용.
2. **도메인 분기 없음(P1)**: 커팅 방식·라벨은 요청 바디가 아니라 **Project 설정**에서 온다. 클라이언트는 도메인을 모른다.
3. **긴 작업은 비동기(02 §4)**: 커팅/내보내기는 즉시 `job_id` 반환 → 클라이언트가 `/jobs/{id}` 폴링.
4. **일관된 에러 형식**: 실패는 아래 공통 에러 스키마로 반환.

---

## 1. 공통 규약

### 1.1 상태 코드
| 코드 | 사용처 |
|---|---|
| 200 OK | 조회·수정 성공 |
| 201 Created | 리소스 생성 성공(Project/Dataset/Upload) |
| 202 Accepted | 백그라운드 Job 수락(커팅/내보내기) |
| 400 Bad Request | 입력 검증 실패(라벨이 label_schema 위반 등) |
| 404 Not Found | 리소스 없음 |
| 409 Conflict | 상태 충돌(예: 이미 처리 중인 Dataset 재처리) |
| 422 Unprocessable Entity | FastAPI 기본 검증 실패(타입 등) |
| 500 Internal Server Error | 서버 오류 |

### 1.2 공통 에러 응답 (`ErrorResponse`)
```json
{ "detail": "사람이 읽을 메시지", "code": "VALIDATION_ERROR" }
```

### 1.3 페이지네이션 (목록 공통 쿼리)
`?limit=50&offset=0` — 응답은 `{ "items": [...], "total": <int> }` 형태(`Page[T]`).

### 1.4 시간·경로
- 모든 datetime은 ISO 8601 UTC 문자열.
- `storage_path`는 **Storage 인터페이스 기준 논리 경로**(로컬/Drive 무관, 02 §6.1). 클라이언트는 실제 FS 경로를 모른다.

---

## 2. 인증 (docs/13 §6 — 배포 환경 전용)

`ACCESS_TOKEN`(백엔드 env)이 설정된 경우에만 활성화된다. **미설정이면 이 절은 없는
것과 같다** (로컬 개발 기본).

- `/api/*` 전 요청: `Authorization: Bearer <token>` 필수. 불일치 → **401**
  `{"detail": "액세스 토큰이 필요합니다.", "code": "UNAUTHORIZED"}`.
- 예외: `/health`(무인증), CORS preflight(OPTIONS).
- 미디어 URL 3종은 `?token=<token>` 쿼리도 허용 (브라우저 네이티브 로딩이 헤더를
  못 붙이므로): `/api/segments/{id}/audio` · `/api/segments/{id}/waveform` ·
  `/api/datasets/{id}/export/download`. **그 외 경로는 쿼리 토큰을 받지 않는다.**

## 2b. 엔드포인트 목록 (요약)

| 영역 | Method | Path | 설명 | 코드 |
|---|---|---|---|---|
| Project | GET | `/api/projects` | 목록 | 200 |
| | POST | `/api/projects` | 생성(도메인 설정 포함) | 201 |
| | GET | `/api/projects/{id}` | 상세 | 200 |
| | PATCH | `/api/projects/{id}` | 설정 수정 | 200 |
| | DELETE | `/api/projects/{id}?confirm=이름` | 전체 삭제 (하위+파일, 이름 확인 필수) | 204/400 |
| Dataset | GET | `/api/projects/{id}/datasets` | 프로젝트의 데이터셋 목록 | 200 |
| | POST | `/api/projects/{id}/datasets` | 데이터셋 생성 | 201 |
| | GET | `/api/datasets/{id}` | 상세 | 200 |
| | GET | `/api/datasets/{id}/segments` | 세그먼트 목록 | 200 |
| | GET | `/api/datasets/{id}/export` | Metadata.csv 내보내기(비동기) | 202 |
| | GET | `/api/datasets/{id}/export/download` | 최근 완료된 CSV 다운로드 | 200 |
| | DELETE | `/api/datasets/{id}?confirm=이름` | 데이터셋 삭제 (세그먼트·원본·CSV 포함) | 204/400 |
| Segment | GET | `/api/segments/{id}/waveform` | 미니 파형 피크 (시각 비교용) | 200 |
| | DELETE | `/api/segments/{id}` | 세그먼트 1개 삭제 (파일 포함) | 204 |
| Upload | POST | `/api/uploads` | 원본 업로드(+메타추출) | 201 |
| | DELETE | `/api/source-files/{id}` | 원본 삭제 (참조 세그먼트 있으면 409) | 204/409 |
| Processing | POST | `/api/datasets/{id}/process` | 커팅 Job 시작 | 202 |
| Job | GET | `/api/jobs/{id}` | Job 상태·진행률 | 200 |
| | GET | `/api/datasets/{id}/jobs` | 데이터셋의 Job 목록 | 200 |
| Segment | PATCH | `/api/segments/{id}/labels` | 라벨 부여/수정 | 200 |
| Stats | GET | `/api/stats` | 전체 대시보드 지표 | 200 |
| | GET | `/api/stats?project_id={id}` | 프로젝트별 지표 | 200 |

---

## 3. Project

### 3.1 POST `/api/projects` — 생성
도메인 설정(P1의 핵심)을 담아 프로젝트를 만든다. 여기 담긴 설정이 이후 모든 동작을 좌우한다.

**요청 `ProjectCreate`**
```json
{
  "name": "지하주차장 비프음",
  "domain": "vehicle",
  "cutting_mode": "fixed_interval",
  "cutting_params": { "interval_sec": 3.0 },
  "naming_pattern": "{date}_{model}_{distance}_{seq:03d}",
  "label_schema": [
    { "key": "distance_m", "type": "number", "required": true },
    { "key": "direction", "type": "enum", "options": ["N","S","E","W"], "required": false }
  ],
  "target_duration_sec": 36000
}
```
- `cutting_mode`: registry 키. `"fixed_interval"` · `"silence_based"` (event는 이후 추가).
- `cutting_params`: 전략별 파라미터(JSON). fixed_interval은 `interval_sec`(필수).
  silence_based는 전부 선택: `silence_threshold_db`(기본 -40) · `min_silence_sec`(0.3) ·
  `min_segment_sec`(0.2) · `max_segment_sec`(없음) · `padding_sec`(0.1).
- `target_duration_sec`(nullable): 대시보드 "업로드 진행률" 분모(05 §4).
- `expected_segments_per_source`(nullable, ≥1): 원본 1개당 기대 조각 수(docs/14).
  설정 시 커팅 완료 후 원본별 실제 조각 수와 비교해 `Job.params.quality_check`에 기록
  (차단 없음 — 경고만). null이면 검사 생략.
- `domain`: **태그일 뿐**. 서버는 이 값으로 분기하지 않는다(P1).

**응답 201 `ProjectRead`**
```json
{
  "id": 1, "name": "지하주차장 비프음", "domain": "vehicle",
  "cutting_mode": "fixed_interval", "cutting_params": { "interval_sec": 3.0 },
  "naming_pattern": "{date}_{model}_{distance}_{seq:03d}",
  "label_schema": [ ... ], "target_duration_sec": 36000,
  "created_at": "2026-07-10T09:00:00Z"
}
```

**검증(400)**: `cutting_mode`가 registry에 없으면 거부. `label_schema` 각 항목은 `key`·`type` 필수, `type`이 `enum`이면 `options` 필수.

### 3.2 PATCH `/api/projects/{id}`
부분 수정(`ProjectUpdate`, 모든 필드 optional). `label_schema` 변경 시 기존 Segment는 소급 검증하지 않는다(경고만).

---

## 4. Dataset

### 4.1 POST `/api/projects/{id}/datasets` — 생성
**요청 `DatasetCreate`**: `{ "name": "v1 초기수집", "version": "v1" }`
**응답 201 `DatasetRead`**: `{ "id", "project_id", "name", "version", "status", "created_at" }`
- `status`: `"collecting" | "processing" | "ready"` (생성 시 `collecting`).

### 4.2 GET `/api/datasets/{id}/segments`
**응답 200 `Page[SegmentRead]`**. `SegmentRead`:
```json
{
  "id": 10, "dataset_id": 2, "filename": "20260710_EV6_10m_001.wav",
  "storage_path": "segments/2/20260710_EV6_10m_001.wav",
  "duration_sec": 3.0, "sample_rate": 44100, "channels": 1,
  "bit_depth": 16, "file_size": 264644, "format": "wav",
  "source_start_sec": 0.0, "labels": { "distance_m": 10 },
  "is_labeled": true, "created_at": "..."
}
```
- `bit_depth`는 압축 포맷에서 **null 가능**(05 검토 결과).

### 4.3 GET `/api/datasets/{id}/export` — CSV 내보내기(비동기)
Dataset의 모든 Segment를 CSV로 생성. 큰 데이터셋 대비 **Job으로 처리**.
**응답 202 `JobRead`**(아래 §7). 완료 후 Job에 결과 경로 포함(`result_path`).
- **경로는 설정 패턴** `EXPORT_PATH_PATTERN`(기본 `exports/{project}/{date}_{dataset}.csv`,
  docs/11 §2)으로 결정 — 예: `exports/심음데이터수집/20260712_v1 초기수집.csv`.
  지원하지 않는 필드가 패턴에 있으면 Job 시작 전 400(fail-fast). 사용 패턴은 Job.params에 기록.
- **CSV 형식**(docs/11 §3·§4): 선두에 출처 3컬럼(`project_name`,`dataset_name`,`dataset_version`),
  `duration_sec`·`source_start_sec`는 소수점 3자리 반올림(DB는 원본 정밀도 유지).
> MVP 소규모에선 동기도 가능하나, 계약을 Job으로 통일해 V2 승격을 쉽게 한다.

### 4.4 GET `/api/datasets/{id}/export/download` — 최근 CSV 다운로드
가장 최근 **완료된(done)** export Job의 `result_path`를 읽어 CSV 파일로 반환한다.
**응답 200** `text/csv` (`Content-Disposition: attachment`). 완료된 export가 없으면 404.
> 폴링으로 Job 완료를 확인한 프론트가 이 URL로 파일을 받는다.

### 4.5 GET `/api/segments/{id}/waveform` — 미니 파형 피크
재생 없이 세그먼트들이 비슷하게 잘렸는지 **눈으로 비교**하기 위한 데이터.
**응답 200 `WaveformRead`**:
```json
{ "segment_id": 10, "duration_sec": 0.36, "peaks": [0.02, 0.31, 0.28, ...] }
```
- `peaks`: 오디오를 60개 구간으로 나눈 구간별 |진폭| 최대값, **풀스케일(1.0) 기준 절대값**.
  세그먼트별 정규화를 하지 않으므로 세그먼트 간 파형 높이를 그대로 비교할 수 있다.
- 세그먼트 파일은 불변이라 `Cache-Control: private, max-age=3600`으로 캐시된다.

---

## 5. Upload

### 5.1 POST `/api/uploads` — 원본 업로드
`multipart/form-data`. 파일과 함께 대상 Project(필수)·Dataset(선택)을 지정한다.

**폼 필드**
| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `files` | file[] | ✓ | 하나 이상의 오디오 파일(wav/mp3/flac/m4a) |
| `project_id` | int | ✓ | 대상 프로젝트 |
| `dataset_id` | int | ✗ | 대상 데이터셋. **없으면 기본 Dataset(v1) 자동 생성**(승인된 결정 4) |

**동작**: 각 파일을 Storage에 저장 → `audio/metadata.py`로 메타 추출 → **SourceFile** + **UploadHistory** 기록 → `on_upload_complete` 훅 발화.

**응답 201 `UploadResult`**
```json
{
  "dataset_id": 2,
  "created_dataset": true,
  "sources": [
    { "id": 5, "filename": "rec_4h.wav", "storage_path": "uploads/2/rec_4h.wav",
      "duration_sec": 14400.0, "sample_rate": 44100, "channels": 2,
      "bit_depth": 16, "file_size": 5079600000, "format": "wav" }
  ]
}
```
- `created_dataset`: 기본 Dataset을 자동 생성했는지 여부.
- 메타 추출은 빠르므로(헤더 읽기) 업로드 응답에 **동기 포함**. 커팅만 비동기.

**검증(400)**: 지원하지 않는 포맷, `project_id` 미존재.
**충돌(409)**: 같은 Dataset에 **같은 파일명이 이미 존재**하면 거부 — 파일을 덮어쓰고
row만 중복되던 사고 방지(docs/12 B2). 재업로드는 기존 원본 삭제 후, 또는 다른 파일명으로.

### 5.2 DELETE — 삭제 계약 (docs/12 B1)
| 엔드포인트 | 규칙 |
|---|---|
| `DELETE /api/segments/{id}` | 세그먼트 1개 + 파일. 204 |
| `DELETE /api/source-files/{id}` | 참조 세그먼트 있으면 **409**(먼저 정리 유도). 204 |
| `DELETE /api/datasets/{id}?confirm=<데이터셋명>` | 이름 불일치 **400**. 세그먼트·원본·export CSV 파일까지 일괄 삭제. 204 |
| `DELETE /api/projects/{id}?confirm=<프로젝트명>` | 이름 불일치 **400**. 모든 dataset 연쇄 삭제. 204 |

- confirm은 **URL 인코딩 필수** (한글 이름을 curl로 보낼 때 `--data-urlencode` — 미인코딩 시 HTTP 파서가 400으로 거부).
- Drive 미러 대상 파일(exports/)은 미러 쪽도 함께 삭제된다(MirrorStorage).

---

## 6. Processing (커팅 — 비동기 Job)

### 6.1 POST `/api/datasets/{id}/process` — 커팅 시작
Dataset의 SourceFile들을 Project 설정의 `cutting_mode`로 커팅한다. **분기문 없음** — registry에서 전략 조회(02 §5).

**요청 `ProcessRequest`**(선택적 오버라이드)
```json
{
  "source_file_ids": [5],
  "params_override": null,
  "common_labels": { "distance_m": 10, "direction": "N" },
  "replace_existing": false,
  "inherit_labels": true
}
```
- 바디 없이 호출하면 Dataset의 모든 SourceFile을 Project 기본 설정으로 처리.
- **재처리 안전장치 (docs/10)**: 대상 원본에 기존 세그먼트가 있으면
  `replace_existing=true` 없이는 **409**로 거부한다(암묵적 라벨 손실·중복 누적 방지).
  대체 시 `inherit_labels=true`(기본)면 기존 라벨을 **시간 겹침 매칭으로 승계**하고,
  `common_labels`는 승계 라벨 위에 덮어쓴다. 두 플래그는 Job.params에 기록된다.
- `params_override`(선택): 이번 Job에 한해 `cutting_params`를 덮어씀(재현성 위해 Job.params에 기록).
- `common_labels`(선택): 이번 커팅으로 생성되는 **모든 Segment에 일괄 부여할 공통 라벨**.
  각 Segment의 `labels`에 그대로 채워지고, `is_labeled`도 이 값 기준으로 계산된다.
  → 업로드 폼에서 "이 녹음은 전부 10m/북쪽"처럼 조건이 동일한 경우를 한 번에 처리(개별 입력 불필요).
  - **검증 규칙**: 제공된 값의 **type/enum 위반만 400**으로 차단한다.
    required 라벨의 **누락은 에러가 아니다** — 라벨 없이 커팅하고 나중에 채우는
    흐름(부분 라벨링)을 허용해야 대시보드 "라벨링 진행률"(is_labeled 비율)이 의미를 가진다.
  - `common_labels`가 required 필드를 모두 채우면 생성 Segment는 `is_labeled=true`,
    일부만 채우면(또는 생략하면) `is_labeled=false`로 시작.
  - 재현성을 위해 `common_labels`도 Job.params에 함께 기록한다.
  - 개별 예외 보정은 이후 `PATCH /segments/{id}/labels`(§8)로 덮어쓴다.

**응답 202 `JobRead`**: 즉시 반환(아래 §7). Dataset.status → `processing`.
**검증(400)**: 아래 두 경우 Job을 시작하지 않고 즉시 거부(fail-fast).
  1. `common_labels`에 제공된 값이 type/enum 위반.
  2. `naming_pattern`이 참조하는 필드를 커팅 시점에 채울 수 없을 때 —
     사용 가능한 값은 `common_labels` + 자동값(`date`, `seq`)뿐이므로,
     패턴이 라벨(예: `{distance_m}`)을 참조하면 그 라벨은 `common_labels`로 반드시 전달해야 한다.
     (그렇지 않으면 백그라운드에서 파일명 생성이 실패하므로 시작 전에 알려준다.)
**충돌(409)**: 해당 Dataset에 이미 `running` 커팅 Job이 있으면 거부.

> 처리 흐름(백그라운드): `queued → running`(전략.cut → Segment 생성 → naming → Storage 저장 → DB 기록, progress 갱신) `→ done/failed` → `on_processing_done` 훅 → Dataset.status `ready`.

---

## 7. Job (진행률·재현성)

### 7.1 GET `/api/jobs/{id}` — 상태 조회(폴링)
**응답 200 `JobRead`**
```json
{
  "id": 7, "dataset_id": 2, "type": "cutting",
  "status": "running", "progress": 320, "total_items": 1000,
  "params": { "cutting_mode": "fixed_interval", "interval_sec": 3.0 },
  "error_msg": null, "result_path": null,
  "started_at": "2026-07-10T09:05:00Z", "finished_at": null
}
```
- `type`: `"cutting" | "export"`.
- `status`: `"queued" | "running" | "done" | "failed"`.
- `progress`/`total_items`: 진행바(예: 320/1000). `total_items`는 시작 후 확정될 수 있어 초기 null 가능.
- `result_path`: export Job 완료 시 CSV 논리 경로.
- `error_msg`: 실패 사유(status=failed).
- `params.quality_check`: 커팅 Job에서 프로젝트에 `expected_segments_per_source`가
  설정된 경우에만 존재(docs/14 §4). 형식:
  ```json
  { "expected": 30, "ok": false,
    "sources": [ { "source_file_id": 5, "filename": "rec.wav",
                   "expected": 30, "actual": 29, "status": "shortfall" } ] }
  ```
  `status`: `"ok" | "shortfall" | "excess"`. 프론트는 `ok=false`면 재녹음 검토 경고를 띄운다.

### 7.2 GET `/api/datasets/{id}/jobs`
**응답 200 `Page[JobRead]`** — 최신순.

---

## 8. Segment 라벨

### 8.1 PATCH `/api/segments/{id}/labels`
> 기본 라벨링은 커팅 시 `common_labels`(§6.1)로 일괄 처리한다. 이 엔드포인트는 **개별 예외 보정용**
> (특정 세그먼트만 값이 다를 때). 공통 라벨 위에 부분 덮어쓰기.

**요청 `LabelUpdate`**: `{ "labels": { "distance_m": 10, "direction": "N" } }`
- 기존 labels 위에 **부분 덮어쓰기(merge)** 후, 병합 결과를 label_schema로 검증.
- 검증 규칙은 §6.1과 동일: 제공된 값의 **type/enum 위반만 400**. required 누락은
  에러가 아니라 `is_labeled=false`로 반영(부분 라벨링 허용).
- 통과 시 `labels` 저장 + `is_labeled` 재계산(모든 required 충족 시 true).

**응답 200 `SegmentRead`**. **검증 실패(400)**: 어떤 key가 왜 틀렸는지 `detail`에 명시.

---

## 9. Stats (대시보드)

### 9.1 GET `/api/stats` (전체) / `?project_id={id}` (프로젝트별)
집계는 `stats_service`가 pandas로 계산(05 §4 지표 전부 커버). **응답 200 `StatsResponse`**
```json
{
  "total_segments": 1000,
  "total_duration_sec": 3000.0,
  "total_size_bytes": 264000000,
  "avg_duration_sec": 3.0,
  "sample_rate_distribution": { "44100": 800, "48000": 200 },
  "format_distribution": { "wav": 1000 },
  "upload_progress": { "current_sec": 3000.0, "target_sec": 36000, "ratio": 0.083 },
  "labeling_progress": { "labeled": 640, "total": 1000, "ratio": 0.64 },
  "recent_uploads": [
    { "filename": "rec_4h.wav", "uploaded_at": "...", "file_size": 5079600000 }
  ],
  "per_project": [
    { "project_id": 1, "name": "지하주차장 비프음", "segment_count": 1000, "duration_sec": 3000.0 }
  ]
}
```
- `upload_progress.target_sec`가 없으면(Project.target_duration_sec null) `ratio`는 null.
- `per_project`는 전체 조회 시에만 채운다.

---

## 10. schema ↔ 파일 배치 (03 구조와 정렬)

| schema 그룹 | 파일 |
|---|---|
| ProjectCreate/Update/Read | `schemas/project.py` |
| DatasetCreate/Read | `schemas/dataset.py` |
| SegmentRead/LabelUpdate | `schemas/segment.py` |
| UploadResult, SourceRead | `schemas/upload.py` |
| JobRead, ProcessRequest | `schemas/job.py` |
| StatsResponse | `schemas/stats.py` |
| ErrorResponse, Page[T] | `schemas/common.py` |

> models(ORM)와 schemas(Pydantic)는 **분리**(CLAUDE.md §4). 위 파일은 전부 Pydantic만.

---

## 11. 확장 자리 (P4 — 지금은 비어 있음)

- **Auth**: 모든 라우터 앞 미들웨어 자리(02 §7). MVP는 무인증.
- **Tool Interface**: `stats_service.get_segment_count(project, filter=...)` 같은 Service 함수를 V2에서 AI 도구로 노출. API는 이미 얇으므로 재사용 가능.
- **Hooks**: `on_upload_complete`/`on_processing_done`/`on_dataset_exported`는 API가 아니라 Service 내부에서 발화 → V2 Notion/Drive 구독.

---

## 다음 단계
이 계약이 확정되면 → **M1 스캐폴딩**부터 계층 순서대로 구현한다(계획 파일 참조).
각 라우트 구현 시 이 문서의 schema를 `schemas/`에 1:1로 옮기고 `response_model`로 지정한다.
