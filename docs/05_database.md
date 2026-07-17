# 05 — 데이터베이스 설계 (Database Design)

> **목적**: `backend/app/models/` 에 들어갈 테이블을 확정한다. 핵심 과제는 **"도메인마다 다른 라벨을
> 테이블 구조 변경 없이 저장하는 것"**. 이것이 DB 차원의 재사용성(P1)이다.
> 연결: 02_architecture.md, 03_structure.md, CLAUDE.md(6장) → (이 문서) → 06_API설계.md

- **MVP DB**: SQLite / **V2**: PostgreSQL (ORM=SQLAlchemy, 마이그레이션=Alembic)

---

## 0. 설계 원칙

1. **3층 뼈대**: Project → Dataset → Segment (PRD 4장).
2. **라벨은 유연 저장(JSON)**: 도메인이 바뀌어도 테이블을 안 바꾼다. → 아래 2장.
3. **재현성**: 무엇을 언제 어떤 설정으로 처리했는지 History/Job에 남긴다.
4. **SQL 종속 회피**: 컬럼 타입·기능은 SQLite와 PostgreSQL 양쪽에서 되는 것만 쓴다.
   (JSON 컬럼은 둘 다 지원. SQLite는 TEXT로, PG는 JSONB로 매핑되게 SQLAlchemy `JSON` 타입 사용.)

---

## 1. 전체 ERD (관계도)

```
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│   Project    │1      *│   Dataset    │1      *│   Segment    │
│──────────────│───────>│──────────────│───────>│──────────────│
│ id (PK)      │        │ id (PK)      │        │ id (PK)      │
│ name         │        │ project_id FK│        │ dataset_id FK│
│ domain       │        │ name         │        │ filename     │
│ cutting_mode │        │ version      │        │ storage_path │
│ cutting_params(JSON)  │ status       │        │ duration_sec │
│ naming_pattern        │ created_at   │        │ sample_rate  │
│ label_schema(JSON)    │              │        │ channels     │
│ created_at   │        └──────┬───────┘        │ bit_depth    │
└──────┬───────┘               │                │ file_size    │
       │                       │                │ format       │
       │                       │                │ source_start_sec │
       │1                      │1               │ labels (JSON) ★  │
       │                       │                │ is_labeled   │
       │*                      │*               │ created_at   │
┌──────▼───────┐        ┌──────▼───────┐        └──────┬───────┘
│ UploadHistory│        │     Job      │               │
│──────────────│        │──────────────│               │ (원본 추적, 선택)
│ id (PK)      │        │ id (PK)      │        ┌──────▼───────┐
│ project_id FK│        │ dataset_id FK│        │ SourceFile   │
│ filename     │        │ type         │        │──────────────│
│ file_size    │        │ status       │        │ id (PK)      │
│ uploaded_at  │        │ progress     │        │ dataset_id FK│
└──────────────┘        │ total_items  │        │ filename     │
                        │ params (JSON)│        │ storage_path │
                        │ error_msg    │        │ duration_sec │
                        │ started_at   │        │ uploaded_at  │
                        │ finished_at  │        └──────────────┘
                        └──────────────┘

★ labels(JSON) = 도메인마다 다른 라벨을 담는 곳. 이 한 칸이 재사용성의 핵심.
```

---

## 2. 재사용성의 열쇠 — 라벨을 JSON으로 저장 (가장 중요)

### 문제
차량음 Segment는 `distance=5, direction=N`, 심음 Segment는 `patient_id=P01, valve=mitral`.
프로젝트마다 라벨 종류가 다르다. 이걸 어떻게 한 테이블에 담나?

### 나쁜 방법 (채택 안 함)
```
Segment 테이블에 distance, direction, patient_id, valve ... 컬럼을 계속 추가
→ 새 도메인마다 ALTER TABLE. 컬럼이 수십 개로 불어나고 대부분 NULL. 재사용성 붕괴.
```

### 채택한 방법 — `labels` JSON 컬럼
```
Segment.labels = {"distance_m": 5, "direction": "N"}        # 차량음
Segment.labels = {"patient_id": "P01", "valve": "mitral"}   # 심음
```
- 테이블 구조는 **영원히 그대로**. 도메인이 뭐가 오든 labels 안에 담는다.
- "어떤 라벨이 있어야 하는가"는 **Project.label_schema(JSON)** 가 정의한다.
  ```
  Project.label_schema = [
    {"key": "distance_m", "type": "number", "required": true},
    {"key": "direction",  "type": "enum", "options": ["N","S","E","W"]}
  ]
  ```
- 앱은 이 schema를 읽어 **입력 폼을 자동 생성**하고, labels가 schema를 만족하는지 검증한다.

### 트레이드오프 (정직하게)
- 장점: 무한한 도메인 확장, 테이블 불변, 폼·검증·CSV 자동화.
- 단점: JSON 내부 값으로 **복잡한 SQL 집계**는 순수 컬럼보다 불편하다.
  → MVP 규모(로컬·소수)에선 문제없다. 대시보드 집계는 파이썬(pandas)에서 처리.
  → V2에서 특정 라벨로 자주 필터링하면, 그 라벨만 별도 인덱스 컬럼으로 승격 가능(후행 최적화).

> 결론: **유연성 > 초기 쿼리 편의**. 연구실은 도메인이 계속 바뀌므로 유연성이 최우선(R1).

---

## 3. 테이블 상세

### 3.1 Project (도메인 설정의 집)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | PK | |
| name | str | 예: "지하주차장 비프음" |
| domain | str | 예: "vehicle","heart","industrial" (분류/필터용 태그일 뿐, 코드 분기 아님) |
| cutting_mode | str | "event" / "silence" / "fixed_interval" |
| cutting_params | JSON | 전략별 파라미터 (interval, threshold 등) |
| naming_pattern | str | 예: `{date}_{model}_{distance}_{seq:03d}` |
| label_schema | JSON | 이 프로젝트가 요구하는 라벨 정의(2장) |
| target_duration_sec | int, null | 목표 총 녹음시간(초) — 대시보드 업로드 진행률 분모 |
| expected_segments_per_source | int, null | 원본 1개당 기대 조각 수 — 커팅 후 품질 검사(docs/14), null이면 검사 생략 |
| created_at | datetime | |

> `domain`은 **태그**다. 코드가 `if domain=="vehicle"` 하지 않는다(CLAUDE.md P1). 필터·표시에만 쓴다.

### 3.2 Dataset (버전 있는 묶음)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | PK | |
| project_id | FK→Project | |
| name | str | 예: "v1 초기수집" |
| version | str | "v1","v2" (V2에서 GitHub 버전과 연결) |
| status | str | "collecting"/"processing"/"ready" |
| created_at | datetime | |

### 3.3 Segment (커팅 조각 = 메타데이터 1행)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | PK | |
| dataset_id | FK→Dataset | |
| filename | str | naming_pattern으로 생성 |
| storage_path | str | Storage 인터페이스 기준 경로(로컬/Drive 무관) |
| duration_sec | float | 자동 추출 |
| sample_rate | int | 자동 추출 |
| channels | int | 자동 추출 |
| bit_depth | int | 자동 추출 |
| file_size | int | bytes, 자동 추출 |
| format | str | "wav" 등 |
| source_start_sec | float | 원본에서 잘린 시작 위치(재현성) |
| labels | JSON | ★ 도메인별 라벨 |
| is_labeled | bool | 라벨링 진행률 계산용 |
| created_at | datetime | |

### 3.4 SourceFile (원본 추적, 선택적이지만 권장)
어떤 원본에서 이 세그먼트들이 나왔는지 기록 → 재현성·재처리에 필요.
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | PK | |
| dataset_id | FK→Dataset | |
| filename | str | 원본 파일명 |
| storage_path | str | |
| duration_sec | float | 원본 총 길이 |
| uploaded_at | datetime | |

### 3.5 Job (비동기 작업 = 재현성 + 진행률)
02 아키텍처 4장의 백그라운드 커팅을 1급 객체로.
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | PK | |
| dataset_id | FK→Dataset | |
| type | str | "cutting","export" 등 |
| status | str | "queued"/"running"/"done"/"failed" |
| progress | int | 처리한 개수 |
| total_items | int | 전체 개수 → 진행률 = progress/total |
| params | JSON | 실행 당시 설정(어떤 전략·파라미터로 돌렸나) |
| error_msg | str/null | 실패 사유 |
| started_at / finished_at | datetime | |

### 3.6 UploadHistory (업로드 이력)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | PK | |
| project_id | FK→Project | |
| filename | str | |
| file_size | int | |
| uploaded_at | datetime | |

> ProcessingHistory는 별도 테이블 대신 **Job**이 그 역할을 겸한다(중복 방지).
> Job의 params/status/finished_at이 곧 "무엇을 언제 어떻게 처리했나"의 기록이다.

---

## 4. 대시보드 지표가 어느 테이블에서 나오는지 (검증)

| 대시보드 지표 | 출처 |
|---|---|
| 총 데이터 개수 | Segment count |
| 총 녹음 시간 | Segment.duration_sec 합 |
| 저장 용량 | Segment.file_size 합 |
| 평균 길이 | Segment.duration_sec 평균 |
| 프로젝트별 현황 | Project별 Segment 집계 |
| 업로드 진행률 | 총 녹음시간 / Project 목표(설정) |
| 라벨링 진행률 | is_labeled=true 비율 |
| Sample Rate 분포 | Segment.sample_rate 그룹핑 |
| 파일 형식 통계 | Segment.format 그룹핑 |
| 최근 업로드 | UploadHistory 최신순 |

→ 모든 지표가 위 테이블로 커버된다. 스키마 누락 없음.

---

## 5. SQLite → PostgreSQL 전환 안전장치

- 모든 테이블은 **SQLAlchemy 모델**로 정의 → SQL을 직접 쓰지 않는다.
- JSON 컬럼은 SQLAlchemy `JSON` 타입 사용 → SQLite는 TEXT, PostgreSQL은 JSONB로 자동 매핑.
- 스키마 변경은 **Alembic 마이그레이션**으로만. → PG 전환은 `DATABASE_URL`만 교체 + 마이그레이션 실행.
- 자동 증가 PK·datetime 등 **양쪽 공통 기능만** 사용(방언 특화 기능 금지).

---

## 6. 이 설계가 원칙을 지키는지 자체 점검
| 원칙 | 근거 |
|---|---|
| 도메인 독립(P1/R1) | labels·label_schema JSON, `domain`은 태그일 뿐 |
| DB 확장(R3) | ORM+Alembic+공통타입, URL 교체로 PG 전환 |
| 재현성 | Job.params, source_start_sec, History |
| 대시보드 충족 | 4장 매핑표 전 지표 커버 |

---

## 다음 단계
테이블이 정해졌으니 이 데이터를 **바깥에 노출하는 창구**를 정의한다 → **06 API 설계**.
각 엔드포인트가 어떤 테이블을 읽고/쓰는지, 요청/응답 schema(Pydantic)를 확정한다.
