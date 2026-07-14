# 13 — 배포 설계 (DP: Vercel 프론트 + Railway 백엔드 + Drive 주 저장소)

> **목적**: 연구실 구성원이 브라우저로 함께 쓰도록 플랫폼을 공개 인터넷에 배포한다.
> 06_API.md 패턴대로 이 문서가 승인되면 그대로 구현한다.
> 연결: 01_PRD.md §6(V2 표의 Auth 자리 일부 선행) · 09_drive_integration.md(Drive 부품 재사용)

- **버전**: v1.0 (설계 검토용)
- **마일스톤 접두사**: `DP-M1` ~ `DP-M5`
- **전제 확인됨**: 연구실 Railway 계정·Vercel 계정 보유, Google Drive 구독(용량 충분),
  연구실 상주 서버 없음. 커팅은 상시 프로세스가 필요해 서버리스 단독 구성 불가(검토 완료).

---

## 1. 배경 (왜 지금)

수집(120조합)이 시작되면 라벨 검수·진행 확인을 여러 명이 해야 하는데, 지금은
localhost라 한 사람만 쓸 수 있다. 연구실에 상주 PC가 없으므로 클라우드 배포가 유일한
공유 경로다. 커팅 Job(수 분짜리 백그라운드 연산)이 있어 상시 컨테이너(Railway)가
필수이고, 파일 용량은 서버 디스크 대신 이미 부품이 있는 Google Drive(V2-3)로 보낸다.

## 2. 목표 / 비목표

### 목표
1. **Vercel**(프론트) + **Railway**(FastAPI+커팅+Postgres) + **Drive**(wav·CSV 주 저장소) 배포.
2. **간단 인증**: 연구실 공용 액세스 토큰 1개. 미설정 시 지금과 100% 동일(로컬 개발 무영향).
3. 로컬 개발 흐름 보존: `STORAGE_MODE` 미설정이면 LocalStorage — 배포 설정이 없으면
   코어는 지금 그대로 동작한다(P4 패턴 유지).

### 비목표 (후속으로 미룸)
- 사용자별 계정·권한(JWT 멀티유저) — PRD의 Auth 마일스톤에서. 지금은 공용 토큰 1개.
- S3류 오브젝트 스토리지 — Drive가 병목이 되면 그때 StorageBackend 구현체 교체로.
- 무중단 배포·오토스케일·모니터링 스택, Celery 승격(단일 인스턴스 전제 유지).
- 기존 로컬 데이터 자동 이관 도구 — **원본 재업로드 + 재커팅**으로 갈음
  (세그먼트·라벨은 커팅+common_labels로 재생성되는 설계라 원본 120개만 옮기면 된다).
- 대형 파일(수 GB·수 시간) 업로드 최적화 — `MAX_UPLOAD_MB` 상한 정책으로 관리.

## 3. 아키텍처

```
[브라우저] ── https ──▶ [Vercel] Next.js 프론트 (무료)
     │                        │ NEXT_PUBLIC_API_URL
     └──── 업로드/재생 ────▶ [Railway] FastAPI + 커팅 Job ──▶ [Railway Postgres] 메타데이터
                                  │  임시디스크 = 커팅 작업장 + 읽기 캐시(LRU)
                                  ▼
                            [Google Drive] uploads/ · segments/ · exports/  ← 주 저장소
```

- 요청 흐름(커팅): 업로드 → Railway 임시디스크 → 커팅 → 조각을 Drive에 저장(재시도 포함)
  → DB에 논리 경로 기록 → 재생/파형/재커팅은 캐시 히트 시 즉시, 미스 시 Drive에서 내려받음.

## 4. 설계 1 — 저장소: Drive 주 저장소 승격 (P3)

- 신설: `storage/cached_drive.py` — `CachedDriveStorage(StorageBackend)`.
  - **진실 원천 = Drive** (V2-3 `GoogleDriveStorage` 재사용).
  - `save`/`save_from_path`: Drive 업로드 **동기 + 재시도**(지수 백오프 3회, 429/5xx 대상).
    성공 시 로컬 캐시에도 기록. **실패 시 예외 = Job 실패** (미러의 "실패 무시"와 다름 — §8 리스크).
  - `read`/`local_path`: 캐시 히트 → 즉시. 미스 → Drive 다운로드 후 캐시.
  - 캐시: 임시 디스크에 LRU, 상한 `CACHE_MAX_MB`(기본 2048). 컨테이너 재시작 시 소실돼도
    무해(다시 받으면 됨).
- 선택 로직(`storage/__init__.py`): `STORAGE_MODE` = `local`(기본) | `drive_primary`.
  기존 `MirrorStorage`(local 주 + Drive 미러)는 local 모드의 옵션으로 그대로 유지.
- **P4 경계 재정의(중요)**: drive_primary 모드에서 Drive는 "외부 연동"이 아니라
  **본 흐름의 저장소 부품**이다. 실패를 숨기지 않고 Job 실패로 드러낸다.
  Notion 훅 등 나머지 외부 연동은 기존 P4 그대로(실패 무시).

## 5. 설계 2 — DB: Postgres 전환 (R3 실행)

- `DATABASE_URL=postgresql+psycopg://...` 교체. **새 라이브러리: `psycopg[binary]`**
  (이 문서 승인 = 라이브러리 승인으로 간주).
- 검증 항목: Alembic 전체 마이그레이션을 빈 Postgres에서 실행, JSON 컬럼(cutting_params·
  label_schema·labels) 동작, 전체 pytest. 테스트 기본은 SQLite 유지(빠름),
  Postgres 검증은 로컬 Docker 컨테이너로 1회 + 골든 패스 스모크(DP-M1 완료 기준).

## 6. 설계 3 — 인증 (새 계약, 06_API.md 갱신 필요)

- `ACCESS_TOKEN`(env) 설정 시에만 활성화되는 미들웨어(P4 패턴 — 미설정 = 지금과 동일):
  - `/api/*` 전부 `Authorization: Bearer <token>` 요구. 불일치 → **401**.
  - 예외: `/health`(모니터링용 무인증).
  - **미디어 예외**: `<audio src>`·파형은 브라우저가 헤더를 못 붙이므로
    `/api/segments/{id}/audio`·`/waveform`·`/export/download`는 `?token=<token>`
    쿼리 파라미터도 허용. (Vercel↔Railway는 도메인이 달라 서드파티 쿠키가 차단되므로
    쿠키 방식은 채택하지 않는다.)
- 프론트: 첫 진입 시 토큰 입력 화면 → `localStorage` 저장 → `api.ts request()`가 헤더
  부착, 미디어 URL 헬퍼가 쿼리 토큰 부착. 401 수신 시 토큰 화면으로 복귀.
- 토큰 교체 = Railway env 변경 + 재배포 + 구성원에게 새 토큰 공지(런북에 절차).

## 7. 설계 4 — 배포 구성

- **backend/Dockerfile**: `python:3.12-slim` + ffmpeg + uv sync. 시작 커맨드:
  `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  (단일 인스턴스라 마이그레이션 경합 없음).
- **Railway**: 서비스 1개 + Postgres 플러그인. 환경변수:
  `DATABASE_URL`(플러그인 주입), `STORAGE_MODE=drive_primary`, `ACCESS_TOKEN`,
  `CORS_ORIGINS=["https://<vercel-도메인>"]`, Drive 4종(GOOGLE_OAUTH_*·DRIVE_ROOT_FOLDER_ID),
  `NOTION_*`(선택), `CACHE_MAX_MB`, `MAX_UPLOAD_MB`.
- **Vercel**: frontend/ 연결, `NEXT_PUBLIC_API_URL=https://<railway-도메인>/api`.
- 업로드 상한: FastAPI에서 `MAX_UPLOAD_MB`(기본 200) 검사 → 초과 시 413 + 안내 메시지.

## 8. 측정 계획 (추측으로 정하지 않는 값들)

| 결정할 것 | 측정 방법 | 반영처 |
|---|---|---|
| Railway 프록시 업로드 한도 | 배포 직후 50/100/200MB 더미 업로드 실측 | `MAX_UPLOAD_MB` 기본값 |
| 재생 첫 로드 지연(Drive 미스) | 배포 환경에서 세그먼트 10개 재생 실측 | 캐시 크기·프리페치 필요성 판단 |
| 커팅 Job 총 시간(Drive 저장 포함) | 3분 파일 1개 실측 (조각 ~30개) | UI 안내 문구·타임아웃 값 |
| Railway 임시 디스크 가용량 | 배포 후 `df` 실측 | `CACHE_MAX_MB` 기본값 조정 |

## 9. 마일스톤 (각각이 승인 게이트)

| 마일스톤 | 내용 | 완료 기준 |
|---|---|---|
| **DP-M1** | Postgres 전환 (+psycopg) | 로컬 Docker Postgres에서 alembic + pytest 전체 green + 골든 패스 스모크 통과 |
| **DP-M2** | 인증 (백엔드 미들웨어 + 프론트 토큰 화면) | 토큰 설정 시 401/200 계약 테스트, 미설정 시 기존 테스트 전부 green, 브라우저 로그인 흐름 확인 |
| **DP-M3** | CachedDriveStorage (주 저장소 승격 + 캐시 + 재시도) | drive_primary 모드로 업로드→커팅→재생→export 골든 패스 **실연동** 통과, 재시도 단위 테스트 |
| **DP-M4** | Railway + Vercel 실배포 | 공개 URL에서 골든 패스 E2E + 연구실원 1명 접속 확인 + §8 실측 완료 |
| **DP-M5** | 문서·운영 마무리 | 06(인증 계약)·02·03·CLAUDE.md 갱신, 운영 런북(재배포·로그 확인·토큰 교체·Drive 장애 시 대응) |

## 10. 알려진 리스크 / 한계

| 리스크 | 완화 | 다음 단계에 미치는 영향 |
|---|---|---|
| Drive API 쿼터·장애가 커팅 실패로 직결 | 재시도 3회 + 실패 시 Job failed로 명시. 장애 장기화 시 `STORAGE_MODE=local`로 임시 회귀 가능 | 수집 당일 장애 시 로컬 모드로 우회하고 나중에 Drive 동기화 |
| 공용 토큰 유출 = 전체 접근 | 토큰 교체 절차 런북화. HTTPS 전제(Railway·Vercel 기본) | 사용자별 계정이 필요해지는 시점에 Auth 마일스톤 착수 |
| 첫 재생 지연(Drive 왕복 수백 ms~수 초) | LRU 캐시. 라벨 검수처럼 반복 청취엔 캐시가 흡수 | 체감 불만 시 프리페치(다음 세그먼트 미리 캐시) 후속 검토 |
| 단일 인스턴스 전제(BackgroundTasks) | 그대로 유지(수 명 규모 충분). 스케일아웃 필요 시 Celery 승격 별도 승인 | 동시 커팅 요청이 많아지면 Job이 순차 지연됨 — 운영상 안내 |
| Railway 사용량 요금 초과 가능성 | Hobby $5 포함분 + 사용량 대시보드 확인을 런북에 포함 | 월 요금이 커지면 Oracle Free VM 이전 재검토 |
| mp3/m4a는 ffmpeg 필요 | Dockerfile에 ffmpeg 포함(문제 없음 — 서버리스가 아니므로) | 없음 |

## 11. CLAUDE.md 갱신 제안 (승인 시 적용할 diff)

```diff
 §4 문서 맵:
+| 13_deployment.md | DP 배포 설계 (Vercel+Railway+Drive 주 저장소·인증) | 배포 작업 시 |

 §11 현재 진행 상황:
+- 🔄 **DP**: 배포 (Vercel+Railway+Drive) — 설계 docs/13 승인, DP-M1부터 진행 예정
```
