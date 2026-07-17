# 15. 수집 진행률(개수) + 업로더 기록 (V2-7)

> 상태: **설계안 (v1.0, 2026-07-17)** — 사용자 결정 반영: 개수 기준=세그먼트,
> 연구원 입력=자유 입력+브라우저 기억, 노출=업로드 이력·원본 목록+Notion 연구노트
> (CSV 컬럼 제외).

## 1. 목표와 범위

두 기능, 모두 **설정이 없으면 기존과 100% 동일 동작** (P4 정신):

- **A. 수집 진행률(개수)**: 프로젝트에 "전체 수집 목표 개수"(세그먼트 기준)를
  설정하면, 대시보드에 **원형 게이지**로 "지금까지 몇 % 수집" 표시.
  (예: 계획 11,520클립 중 3,456개 → 30%)
- **B. 업로더 기록**: 업로드 화면에 "연구원 이름" 입력 칸. 원본·업로드 이력에
  남고, Notion 연구노트 자동기록에도 업로드 줄이 추가된다.

**비목표**: 로그인/계정(자기 신고 방식 — 공용 토큰 체제 유지), CSV export 컬럼
추가(사용자 결정으로 제외), 업로더별 통계 화면.

## 2. 데이터 모델 (docs/05 갱신 대상)

| 테이블 | 추가 컬럼 | 타입 | 설명 |
|---|---|---|---|
| Project | `target_segment_count` | int, null | 전체 수집 목표(세그먼트 개수). null이면 게이지 없음 |
| SourceFile | `uploaded_by` | str(100), null | 업로드한 연구원 이름(자기 신고) |
| UploadHistory | `uploaded_by` | str(100), null | 〃 (이력에도 함께 — 원본 삭제 후에도 남는 기록) |

마이그레이션 1개(nullable 3컬럼 — 기존 데이터 무영향).

## 3. API (docs/06 갱신 대상)

- `POST/PATCH /api/projects`: `target_segment_count`(선택, ≥1) 추가.
  기존 `target_duration_sec`(시간 기준)·`expected_segments_per_source`(원본당
  품질 검사)와 **역할이 다름** — 문서에 3필드 비교표를 넣는다.
- `POST /api/uploads`: Form 필드 `uploaded_by`(선택, str) 추가.
  → `SourceRead`에 `uploaded_by` 노출.
- `GET /api/stats`: `collection_progress { collected, target, ratio }` 추가.
  - `collected` = 세그먼트 수(기존 total_segments와 동일 집계, 프로젝트 필터 반영).
  - `target`: 프로젝트 범위 조회는 그 프로젝트 값, 전체 조회는 설정된 프로젝트
    합계 (upload_progress.target_sec과 같은 규칙 — stats_service 기존 패턴).
  - `recent_uploads[]`에 `uploaded_by` 추가.

## 4. 프론트

| 위치 | 변경 |
|---|---|
| ProjectForm | "전체 수집 목표(세그먼트 개수, 선택)" 숫자 입력 1개 |
| 대시보드 | `ProgressStat variant="gauge"`(기존 라벨링 게이지와 동일 부품)로 "수집 진행률" 원형 게이지 추가 — target 없으면 비표시 |
| UploadForm | "연구원 이름(선택)" 텍스트 입력 — `localStorage("uploader_name")`에 기억, 다음부터 자동 채움 |
| 업로드 결과 목록 | 파일 정보 뒤에 업로더 이름 표시 (구현 시 확인: 데이터셋 상세에 원본 목록 UI가 원래 없어 이곳으로 조정 — `SourceRead`에는 포함되므로 추후 목록 UI가 생기면 바로 표시 가능) |
| 대시보드 최근 업로드 | 파일명 옆에 업로더 이름 |

## 5. Notion 연구노트 (P4 — 플러그인만 수정)

`hooks/notion.py`에 `on_upload_complete` 구독자 추가:
자동기록 섹션에 `"{시각} — 업로드: {파일명들} ({용량}) — 연구원: {이름 or 미기재}"`
한 줄 append. 토큰 없으면 기존처럼 no-op, 실패는 로그만.

## 6. 마일스톤

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| **C-M1** | 모델 3컬럼 + 마이그레이션 + 스키마 + stats/uploads 서비스 | 전체 pytest green (신규 테스트 포함) |
| **C-M2** | 프론트 5곳 + 빌드 | `npm run build` + 격리 브라우저 검증(게이지 %·업로더 표시 스크린샷) |
| **C-M3** | Notion 업로드 기록 + 실배포 | 실서버에서 업로드→Notion 블록 확인, Railway/Vercel 재배포 |

## 7. 리스크 / 한계

| 항목 | 내용 |
|---|---|
| 자기 신고 정확성 | 로그인이 없어 이름을 안 적거나 다르게 적을 수 있음 — 브라우저 기억으로 완화, 강제는 비목표 |
| 게이지 이중화 | 진행률 지표가 시간(업로드)·개수(수집)·라벨링 3개가 됨 — 대시보드 배치는 C-M2에서 실화면 보고 조정 |
| 세그먼트 삭제 시 | 게이지 %가 내려감(정상 — 실제 보유 수 기준) |
