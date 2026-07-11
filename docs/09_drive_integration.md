# 09 — Google Drive 연동 설계 (V2-3: MirrorStorage)

> **목적**: metadata.csv를 Google Drive로 **자동 동기화**하는 V2-3의 계약을 확정한다
> (wav 미러는 설정으로 나중에 켤 수 있는 구조). 07(Notion)과 같은 방식 — 승인되면 그대로 구현.
> 연결: 01_PRD §6 · 02_architecture §6.1(StorageBackend) → (이 문서)
> ※ 번호 참고: 08은 커팅 튜닝 가이드가 사용 중이라 09로 부여.

- **버전**: v1.0
- **원칙(P3·P4)**: Drive는 `StorageBackend` **인터페이스 뒤에** 들어간다 — Service·worker 코드
  무변경. 자격증명이 없으면 지금의 LocalStorage 그대로 동작한다(플러그인).

---

## 1. 목표와 범위

### 하는 것
1. **CSV 미러 백업**: `exports/`(metadata.csv)가 로컬에 저장될 때마다 Drive의 지정 폴더에
   **비동기로 복사**된다. 같은 이름은 덮어쓰기(재export 시 최신본 유지), 삭제도 미러.
2. **폴더 구조**: Drive 루트 폴더 아래 **논리 경로 그대로** —
   기본 패턴 기준 `{루트}/exports/{프로젝트명}/{날짜}_{데이터셋명}.csv`
   (경로 패턴은 `EXPORT_PATH_PATTERN` 설정, docs/11 §2).

### 안 하는 것 (비목표)
- **세그먼트 wav(`segments/`) 미러** — 플랫폼에서 이미 재생 가능하므로 백업 필요성이 낮고,
  용량·업로드 시간 부담만 크다. **필요해지면 `.env`의 `DRIVE_MIRROR_PREFIXES`에
  `segments`를 추가하는 것만으로 활성화**된다(코드 변경 0 — 미러 대상은 설정이다).
- **원본(`uploads/`) 미러** — 4시간 녹음은 수 GB. 위와 동일하게 설정으로 추가 가능.
- Drive → 로컬 방향 동기화(단방향 미러 전용), 실패 재시도 큐(로그만 남기고 유실 허용 —
  로컬이 원본이므로 재export로 언제든 재생성 가능), 완전 교체 모드(모든 I/O를 Drive로).
- "프로젝트별 폴더" 재배치 — Storage 계층은 DB(프로젝트)를 모른다(P2). 미러는 저장소
  레이아웃(dataset 단위)을 그대로 따른다. 프로젝트별 뷰가 필요하면 후속에서 Service 계층이 담당.

> **왜 CSV만인데도 MirrorStorage 구조를 유지하나**: 미러 대상이 prefix 설정이라
> segments/uploads 재활성화가 설정 한 줄이고, Storage 인터페이스(P3) 뒤에 있어
> Service·worker가 영원히 무변경이기 때문. 구조는 그대로, 기본 범위만 가볍게 간다.

### 왜 MirrorStorage인가 (완전 교체가 아니라)
02 §6.1의 원래 그림은 "구현체 교체"지만, 완전 교체는 업로드마다 수 GB를 Drive에 올리고
커팅 때 다시 내려받는 구조가 된다(로컬 연구실 워크플로우와 충돌). MirrorStorage는
**인터페이스는 그대로 지키면서**(P3) 로컬을 주 저장소로, Drive를 비동기 미러로 둔다:
읽기·커팅은 로컬 속도, Drive는 백업·공유 가치만 가져간다.

---

## 2. 인증 — OAuth 설치형 앱 (개인 Gmail 확정에 따른 결정)

| 후보 | 판정 |
|---|---|
| 서비스 계정 | ❌ SA가 올린 파일은 SA 소유(자체 15GB 쿼터). 공유 드라이브로 풀 수 있지만 **개인 Gmail은 공유 드라이브 불가** |
| **OAuth (채택)** | ✅ 파일이 사용자 본인 My Drive에 저장(본인 쿼터·바로 보임). 1회 브라우저 동의 후 refresh token으로 무인 운영 |

### 설계 결정 상세
- **스코프**: `https://www.googleapis.com/auth/drive.file` — **앱이 만든 파일만** 접근하는
  비민감(non-sensitive) 스코프. Drive 전체 권한을 요구하지 않아 안전하고,
  비민감 스코프라 Google 앱 검증 없이 프로덕션 게시가 가능하다.
- **refresh token 수명**: OAuth 동의 화면을 "테스트" 상태로 두면 7일마다 만료된다 →
  **"프로덕션"으로 게시**(비민감 스코프라 검증 불필요)하면 장기 유지.
- **라이브러리: 추가 의존성 0.** refresh token → access token은
  `POST https://oauth2.googleapis.com/token` 단순 폼 POST라 기존 httpx로 충분하다.
  (당초 google-auth를 승인받았으나 OAuth 확정으로 불필요해짐 — SA로 바꿀 일이 생기면 그때 도입.)

### 1회 설정 절차 (사용자)
1. [console.cloud.google.com](https://console.cloud.google.com) → 새 프로젝트 → **Google Drive API 활성화**.
2. OAuth 동의 화면: External, 앱 이름 입력 → **게시 상태 "프로덕션"으로 전환**.
3. 사용자 인증 정보 → OAuth 클라이언트 ID 생성 (**유형: 데스크톱 앱**) → client_id/secret 확보.
4. `uv run python scripts/setup_drive_auth.py` (구현 시 제공) — 브라우저 동의 1회 →
   refresh token 출력 → `backend/.env`에 기록.
5. Drive에 백업 루트 폴더 생성(예: "AudioPlatform 백업") → 폴더 URL의 ID를 `.env`에.
   ※ drive.file 스코프는 앱이 만든 파일만 보므로, 루트 폴더도 setup 스크립트가 만들어
   ID를 출력하는 방식을 기본으로 한다(수동 생성 폴더는 앱이 못 봄 — 흔한 함정).

### 공유 드라이브 전환 로드맵 (개인 Gmail → 연구실 Workspace, 계획된 미래)

**질문: "폴더를 공유 드라이브로 옮기기만 하면 되나?" → 아니다.** 두 가지 이유:
1. `drive.file` 스코프는 **앱이 만든 항목만** 접근한다. 공유 드라이브의 루트/기존 폴더는
   이 앱이 만든 게 아니므로 OAuth 토큰으로는 보이지 않는다.
2. 개인 소유 폴더를 공유 드라이브 안으로 옮기면 소유권이 조직으로 넘어가는데, 일반
   사용자는 폴더 단위 이동이 제한되는 등 Drive 정책 변수가 많다.

**전환 시 올바른 경로 (권장): 서비스 계정 + 공유 드라이브** — Workspace가 생기는 순간,
§2 표에서 원래 최적이었던 조합으로 갈아탄다:
1. GCP에서 서비스 계정 생성 → JSON 키 발급.
2. 공유 드라이브에 SA 이메일을 **콘텐츠 관리자 멤버로 추가** (동의 화면·검증·토큰 만료 전부 무관).
3. `.env` 교체: OAuth 3종 → SA 키 경로, `DRIVE_ROOT_FOLDER_ID` → 공유 드라이브 내 폴더 ID.
4. 과거 CSV는 로컬이 원본이므로 **재export로 재미러**하거나 Drive UI에서 파일만 끌어 옮긴다.

**지금 설계에 심어두는 전환 대비 (코드가 미래를 아는 부분):**
- 모든 Drive API 호출에 `supportsAllDrives=true`를 **처음부터 포함** — 개인 Drive에서는
  무해하고, 공유 드라이브에서는 필수. 전환 때 코드 수정 지점을 없앤다.
- **토큰 발급을 단일 함수로 격리** (`_get_access_token()`): OAuth refresh든 SA JWT든
  이 함수 하나만 교체 대상. SA 전환 시 google-auth를 그때 도입하고 이 함수에만 분기 추가.
- 루트는 항상 **폴더 ID 설정**으로 지정 — 개인/공유 드라이브 어느 쪽이든 ID만 갈아끼움.

→ 결론: 전환 비용 = **GCP에서 SA 만들기 + .env 교체 + (선택) 재export.**
Service·worker·MirrorStorage 로직은 무변경.

---

## 3. 아키텍처 — MirrorStorage (P3 준수)

```
Service / worker  ──  storage.save(path, ...)   ← 호출부는 지금과 100% 동일
                          │
                 [MirrorStorage : StorageBackend]
                          │
        ┌─────────────────┼──────────────────────────┐
        ▼ (동기, 항상)                                 ▼ (비동기, mirror 대상 prefix만)
  LocalStorage (주 저장소)                    데몬 스레드 → GoogleDriveStorage.upload
  save/read/local_path/exists/list/delete       (실패 = 로그만, 본 흐름 무영향)
```

- **쓰기**(`save`/`save_from_path`): 로컬 저장 완료 → 경로가 미러 prefix(기본 `exports/`)에
  해당하면 데몬 스레드로 Drive 업로드 큐잉(Notion `_spawn` 패턴 재사용).
- **읽기**(`read`/`local_path`/`exists`/`list`): **로컬만**. Drive를 절대 조회하지 않는다.
- **삭제**(`delete`): 로컬 삭제 + (미러 대상이면) Drive 쪽도 비동기 삭제.
- **선택 로직**: `get_storage()`가 `drive_enabled`면 `MirrorStorage(local, drive)`,
  아니면 지금처럼 `LocalStorage` — 호출부 무변경(P4).

### GoogleDriveStorage 내부 (Drive REST API)
- Drive는 경로가 아닌 **폴더 ID 체계** → 논리 경로의 디렉터리 부분을 폴더 체인으로 해석,
  `files.list`(이름+부모 검색)로 찾고 없으면 `files.create`(folder)로 생성. **폴더 ID 캐시**
  (dict)로 반복 조회 방지.
- 업로드: `POST /upload/drive/v3/files?uploadType=multipart` (메타데이터+바이트).
  같은 이름 존재 시 **덮어쓰기**(기존 file_id에 `PATCH /upload/.../files/{id}` update) —
  재export 시 중복 파일 방지, 항상 최신 CSV 유지.
- 삭제: 이름+부모로 검색 → `DELETE /drive/v3/files/{id}`. 없으면 무시.
- 토큰: access token(수명 1h)을 만료 60초 전까지 캐시, 만료 시 refresh POST로 갱신.
  발급은 `_get_access_token()` 단일 함수로 격리(§2 전환 로드맵 — SA 전환 시 교체 지점).
- **모든 호출에 `supportsAllDrives=true`** (목록 조회는 `includeItemsFromAllDrives=true`도) —
  공유 드라이브 전환 대비, 개인 Drive에서는 무해(§2).

---

## 4. 설정 (backend/.env)

| 키 | 기본값 | 설명 |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | `""` | 데스크톱 앱 클라이언트 ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `""` | |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | `""` | setup 스크립트가 발급 |
| `DRIVE_ROOT_FOLDER_ID` | `""` | 백업 루트 폴더 ID (개인/공유 드라이브 어느 쪽이든 ID만 지정) |
| `DRIVE_MIRROR_PREFIXES` | `["exports"]` | 미러 대상 prefix. **wav가 필요해지면 `segments` 추가만으로 활성화** |
| `DRIVE_TIMEOUT_SEC` | `30.0` | 업로드 타임아웃 (CSV는 여유값; segments 활성화 대비 넉넉히) |

- **활성화 조건**: `drive_enabled` property = OAuth 3종 + 루트 폴더 ID **모두** 존재.
- 미설정 시: `get_storage()`가 LocalStorage 반환 — 지금과 완전 동일(P4).

---

## 5. 파일 배치 (03 구조 준수)

| 파일 | 역할 |
|---|---|
| `storage/drive.py` | `GoogleDriveStorage` — 기존 빈 골격을 실제 구현으로 교체 (토큰 캐시·폴더 해석·업로드/삭제) |
| `storage/mirror.py` | `MirrorStorage(StorageBackend)` — 로컬 위임 + 비동기 미러 |
| `storage/__init__.py` | `get_storage()`에 drive_enabled 분기 |
| `core/config.py` | §4 설정 6키 + `drive_enabled` |
| `scripts/setup_drive_auth.py` | 1회 인증 헬퍼(브라우저 동의 → refresh token + 루트 폴더 생성) ※ scripts/는 신설 — 운영 도구 자리 |
| `tests/test_drive_storage.py` | §6 테스트 |

**변경 없는 것**: services/worker/api/hooks 전부. `StorageBackend` 인터페이스도 무변경.

---

## 6. 테스트 전략 (실 Drive 불필요)

- `GoogleDriveStorage(transport=httpx.MockTransport)` 주입(Notion과 동일 패턴):
  토큰 refresh 요청, 폴더 탐색/생성 쿼리, multipart 업로드 페이로드, 덮어쓰기 경로 검증.
- `MirrorStorage` 단위: 로컬 위임 정확성, **미러 prefix 필터**(exports만 큐잉,
  segments/uploads는 안 됨 — 그리고 prefix 설정 변경 시 segments도 큐잉되는지),
  `_spawn` 동기 패치로 업로드/삭제 큐잉 검증, Drive 실패가 save를 깨지 않음.
- `get_storage()` 분기: 자격 없음 → LocalStorage / 있음 → MirrorStorage.
- 기존 테스트 보호: 테스트 Settings는 Drive 자격이 없으므로 자동으로 LocalStorage 경로 —
  기존 93개 무영향(확인 항목).

---

## 7. 작업 순서 (Milestones)

- **D-M1. 설정+분기 골격**: config 6키·`drive_enabled`, `get_storage()` 분기(아직 Local만),
  기존 테스트 green.
- **D-M2. GoogleDriveStorage**: 토큰 캐시·폴더 해석·업로드/덮어쓰기/삭제 + MockTransport 테스트.
- **D-M3. MirrorStorage**: 위임+prefix 필터+비동기 미러 + 테스트.
- **D-M4. setup 스크립트** + `.env.example` 갱신.
- **D-M5. 실연동**: 사용자 GCP 설정(§2 절차 1~3) → 스크립트로 토큰·폴더 준비 →
  CSV export 1회 → Drive에 `exports/{dataset_id}/metadata.csv` 등장 확인 →
  재export로 **덮어쓰기**(중복 없이 최신본 갱신) 확인.
- **D-M6. 문서 마무리**: 02 §6.1·03 트리·CLAUDE.md 현재 단계 갱신, 커밋.

---

## 8. 한계·트러블슈팅 (구현 후 보강)

| 증상 | 원인 | 해결 |
|---|---|---|
| `invalid_grant` | refresh token 만료(테스트 모드 7일) 또는 회수 | 동의 화면 프로덕션 게시 확인 → setup 스크립트 재실행 |
| 업로드된 파일이 Drive에서 안 보임 | drive.file 스코프는 앱 생성 파일만 접근 — 루트 폴더를 수동 생성함 | setup 스크립트가 만든 폴더를 사용 |
| 서버 종료 직후 일부 미러 유실 | 데몬 스레드 특성(§1 비목표) | 로컬 원본으로 재커팅/재export 시 재미러됨 |
| 403 quota | 개인 계정 쿼터 초과 | 미러 prefix 축소 또는 Drive 정리 |
