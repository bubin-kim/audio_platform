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

## 2. 엔드포인트 목록 (요약)

| 영역 | Method | Path | 설명 | 코드 |
|---|---|---|---|---|
| Project | GET | `/api/projects` | 목록 | 200 |
| | POST | `/api/projects` | 생성(도메인 설정 포함) | 201 |
| | GET | `/api/projects/{id}` | 상세 | 200 |
| | PATCH | `/api/projects/{id}` | 설정 수정 | 200 |
| Dataset | GET | `/api/projects/{id}/datasets` | 프로젝트의 데이터셋 목록 | 200 |
| | POST | `/api/projects/{id}/datasets` | 데이터셋 생성 | 201 |
| | GET | `/api/datasets/{id}` | 상세 | 200 |
| | GET | `/api/datasets/{id}/segments` | 세그먼트 목록 | 200 |
| | GET | `/api/datasets/{id}/export` | Metadata.csv 내보내기(비동기) | 202 |
| | GET | `/api/datasets/{id}/export/download` | 최근 완료된 CSV 다운로드 | 200 |
| Upload | POST | `/api/uploads` | 원본 업로드(+메타추출) | 201 |
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
- `cutting_mode`: registry 키. MVP는 `"fixed_interval"`(silence/event는 이후 추가).
- `cutting_params`: 전략별 파라미터(JSON). fixed_interval은 `interval_sec`.
- `target_duration_sec`(nullable): 대시보드 "업로드 진행률" 분모(05 §4).
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
Dataset의 모든 Segment를 `data/exports/`에 Metadata.csv로 생성. 큰 데이터셋 대비 **Job으로 처리**.
**응답 202 `JobRead`**(아래 §7). 완료 후 Job에 결과 경로 포함(`result_path`).
> MVP 소규모에선 동기도 가능하나, 계약을 Job으로 통일해 V2 승격을 쉽게 한다.

### 4.4 GET `/api/datasets/{id}/export/download` — 최근 CSV 다운로드
가장 최근 **완료된(done)** export Job의 `result_path`를 읽어 CSV 파일로 반환한다.
**응답 200** `text/csv` (`Content-Disposition: attachment`). 완료된 export가 없으면 404.
> 폴링으로 Job 완료를 확인한 프론트가 이 URL로 파일을 받는다.

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

---

## 6. Processing (커팅 — 비동기 Job)

### 6.1 POST `/api/datasets/{id}/process` — 커팅 시작
Dataset의 SourceFile들을 Project 설정의 `cutting_mode`로 커팅한다. **분기문 없음** — registry에서 전략 조회(02 §5).

**요청 `ProcessRequest`**(선택적 오버라이드)
```json
{
  "source_file_ids": [5],
  "params_override": null,
  "common_labels": { "distance_m": 10, "direction": "N" }
}
```
- 바디 없이 호출하면 Dataset의 모든 SourceFile을 Project 기본 설정으로 처리.
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
