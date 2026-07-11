# 11 — CSV Export 개선 설계 (V2-5: 경로·정밀도·자기서술)

> **목적**: Drive에 미러되는 metadata.csv를 "사람이 봐도, 프로그램이 읽어도" 명확하게 만든다.
> 승인되면 그대로 구현한다. 연결: 06_API.md §4.3 · 09_drive_integration.md §1 → (이 문서)

- **버전**: v1.0 (설계 검토용)

---

## 1. 문제 (현재 상태)

1. **경로가 불투명**: `exports/5/metadata.csv` — "5"가 어느 프로젝트인지 Drive에서 알 수 없다.
2. **부동소수점 노이즈**: `duration_sec=0.36002267573696145` 같은 15자리 소수가 CSV를 어지럽힌다.
3. **CSV가 자기 출처를 모른다**: 파일을 옮기거나 이름을 바꾸면 어느 프로젝트/데이터셋 것인지
   알 길이 없다.

---

## 2. 설계 1 — 경로 패턴 (설정 주도, P1)

### 패턴은 설정이다 (하드코딩 금지)

`core/config.py`에 전역 설정 추가 (.env로 변경 가능):

```
EXPORT_PATH_PATTERN = "exports/{project}/{date}_{dataset}.csv"   # 기본값
```

**사용 가능한 플레이스홀더** (worker가 DB에서 채움 — 경로 결정은 DB를 아는 계층에서, P2 준수):

| 필드 | 값 | 예 |
|---|---|---|
| `{project}` | Project.name (치환 후) | `심음데이터수집` |
| `{dataset}` | Dataset.name (치환 후) | `v1_초기수집` |
| `{version}` | Dataset.version | `v1` |
| `{date}` | export 실행일 YYYYMMDD | `20260712` |
| `{project_id}` / `{dataset_id}` | 숫자 id | `3` / `5` |

기본 패턴 적용 결과: `exports/심음데이터수집/20260712_v1 초기수집.csv`

- **fail-fast**: 패턴에 알 수 없는 필드가 있으면 export 시작 전에 400
  (커팅의 naming_pattern 검증과 동일한 방식 — `pattern_fields()` 재사용).
- **범위**: 전역 설정으로 시작한다. 프로젝트별로 다른 export 규칙이 실제로 필요해지면
  그때 Project 컬럼으로 승격(마이그레이션 1개) — 지금 넣는 것은 과설계로 판단(비목표).

### 값 치환(sanitization) — 경로 구성요소 단위

새 순수 함수 `audio/naming.py::render_path(pattern, values)`:

- 패턴의 `/`는 디렉터리 구분자로 **유지**, 채워지는 **값 안의** `/ \ : * ? " < > |` 와
  선행 `.`은 `_`로 치환 (예: 프로젝트명 `차량/A팀` → `차량_A팀`).
- 한글·공백은 유지 (로컬 FS·Drive 모두 문제없음).
- 치환 후 구성요소가 비면 `_`로 대체. 기존 `render_filename`의 치환 규칙을 공유(중복 제거).

### 파급 효과 (의도된 것)

| 항목 | 변화 |
|---|---|
| 로컬 `data/exports/` 레이아웃 | Drive와 동일하게 새 구조 적용 (미러는 논리 경로 1:1이므로) |
| Drive 미러 | `DRIVE_MIRROR_PREFIXES=["exports"]` 그대로 동작 — 기본 패턴이 `exports/`로 시작하므로. 패턴을 바꿀 때 `exports/` 밖으로 나가면 미러가 안 됨을 문서에 명시 |
| **`{date}` 포함의 의미** | 같은 날 재export는 **덮어쓰기**(현행 유지), 날짜가 바뀌면 **새 파일** = 일별 스냅샷이 쌓인다 (라벨 이력의 자연 백업 — docs/10 §6과 시너지). 오래된 스냅샷 정리는 수동 (비목표) |
| 기존 파일 | `exports/{id}/metadata.csv`는 그대로 둔다(이관 없음). 과거 Job의 다운로드는 `result_path`로 여전히 동작 |
| 다운로드 API | 변경 없음 — `job.result_path`를 읽으므로 경로 형태 무관 (확인 완료) |

---

## 3. 설계 2 — 실수 값 반올림

- `build_metadata_csv`에서 **CSV에 쓸 때만** `duration_sec`·`source_start_sec`를
  소수점 3자리로 반올림 (1ms 해상도 — 오디오 연구에 충분).
- **DB는 원본 정밀도 유지** (반올림은 표현 계층에서만 — 재커팅·통계는 원본 사용).
- 라벨 값(labels JSON)은 사용자 데이터이므로 **건드리지 않는다**.

---

## 4. 설계 3 — CSV 자기서술: 메타 행 vs 경로 vs **컬럼 (추천)**

세 방식 비교:

| 방식 | 사람 가독성 | `pd.read_csv()` 기본 호출 | 파일 이동/개명 후 출처 유지 | 여러 CSV 합치기 |
|---|---|---|---|---|
| ① 헤더 위 메타 행 (`# project: ...`) | ○ | **✗ 깨짐** — 첫 행이 헤더로 오인됨. `comment='#'` 옵션을 알아야만 안전 | ○ | △ (전처리 필요) |
| ② 경로/파일명만 | ○ (경로 볼 때만) | ○ | **✗** — 옮기면 출처 소실 | ✗ |
| ③ **메타데이터 컬럼 추가 (추천)** | ○ | **○ 그대로 동작** | ○ | **◎ concat만 하면 출처 유지** |

**추천: ③ 컬럼 추가.** CSV 맨 앞에 `project_name`, `dataset_name`, `dataset_version`
3개 컬럼을 넣는다 (모든 행 동일 값).

- 사용자가 우려한 그대로다 — ①은 `pd.read_csv(path)` 기본 호출이 깨진다.
  `comment='#'`를 아는 사람만 안전한 형식은 연구실 공유 파일로 부적합(R6).
- ③의 비용은 행당 수십 바이트 중복뿐(연구실 규모에서 무의미), 이득은:
  파일이 어디로 가든 출처가 살아있고, **여러 데이터셋 CSV를 `pd.concat`으로 합쳐도
  프로젝트/데이터셋 구분이 유지**된다(tidy data 원칙) — 도메인 간 비교 분석에 즉시 유용.
- ①(메타 행)은 채택하지 않는다. ②는 경로 설계(§2)로 이미 확보되므로 ③과 자연히 병행된다.

결과 CSV 형태:

```csv
project_name,dataset_name,dataset_version,id,filename,...,duration_sec,...,distance_m
심음데이터수집,v1 초기수집,v1,25,20260711_001.wav,...,0.36,...,10
```

---

## 5. 구현 배치 (03 구조 준수)

| 파일 | 변경 |
|---|---|
| `core/config.py` | `export_path_pattern` 설정 (기본 `exports/{project}/{date}_{dataset}.csv`) |
| `audio/naming.py` | `render_path()` 순수 함수 + 치환 규칙 공유 리팩터 |
| `background/worker.py` | `_run_export`: dataset/project에서 값 조립 → `render_path`로 경로 결정 |
| `services/dataset_service.py` | `build_metadata_csv`: 선두 3컬럼 추가 + float 3자리 반올림. `start_export`에서 패턴 fail-fast 검증 |
| `docs/06_API.md` §4.3 | result_path 예시 갱신 |
| `docs/09` §1 | 폴더 구조 예시 갱신 |
| `tests/` | render_path 치환(특수문자·한글·빈 값), 반올림, 3컬럼, 경로 통합, 잘못된 패턴 400 |

**변경 없는 것**: 모델·마이그레이션·Storage 계층·다운로드 API.

---

## 6. 작업 순서

- **E-M1**: `render_path` + 설정 + fail-fast 검증 + 단위 테스트
- **E-M2**: CSV 빌더(3컬럼·반올림) + worker 경로 적용 + 통합 테스트
- **E-M3**: 실검증 — export 실행 → 로컬·Drive에서
  `exports/심음데이터수집/20260712_v1 초기수집.csv` 확인, pandas 기본 read_csv 왕복 확인
- **E-M4**: 문서(06·09) 갱신 + CLAUDE.md §11 + 커밋
