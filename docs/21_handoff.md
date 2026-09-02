# 21. 인수인계 (다른 계정/컴퓨터에서 이어받기)

> **목적**: 이 저장소를 처음 여는 Claude Code 세션이 **이 문서 하나로** 현재 위치를
> 파악하고 바로 이어서 작업할 수 있게 한다.
> **마지막 갱신**: 2026-08-26 (NAS 자체 호스팅 전환 + 1~4일차 216개 원본
> 전체를 nperseg=4096으로 재커팅 완료한 시점)

---

## 0. 제일 먼저 (순서대로)

1. `CLAUDE.md` **§11 현재 진행 상황** — 어디까지 됐는지
2. 이 문서 **§3 지금 하던 일** — 다음에 뭘 할지
3. `git log --oneline -5` — §11의 해시와 실제 이력이 맞는지 확인
4. 진행 중인 주제의 설계 문서(§4 문서 맵)

**세션 시작 시 코드부터 고치지 말 것.** 위 4개를 읽고 현황을 파악한 뒤 시작한다.

---

## 1. 한 문단 요약

대학 연구실용 **오디오 데이터셋 관리 플랫폼**. 수집→전처리→자동 커팅→메타데이터→
데이터셋→연구기록을 자동화한다. **어떤 오디오 도메인에도 재사용**되어야 하므로
도메인 값(대역·임계값·라벨)은 전부 **Project 설정**에 두고 코드에 도메인 분기문을
넣지 않는다(하드룰 P1).

현재 실제 연구 주제는 **아파트/주차장 환경의 경보음(2000Hz 부근) 탐지**지만,
그것은 이 플랫폼의 **한 사용 사례일 뿐**이다.

---

## 2. 환경 준비 (새 컴퓨터)

```bash
git clone https://github.com/bubin-kim/audio_platform.git
cd audio_platform

# 백엔드 (uv 필요)
cd backend && uv sync
uv run pytest -q            # 227 passed 나와야 정상

# 프론트
cd ../frontend && npm install

# 개발 서버 (백엔드 :8100 + 프론트 :3100 한 번에)
cd .. && ./scripts/dev.sh
```

**비밀값은 저장소에 없다.** `ACCESS_TOKEN`·`NOTION_API_KEY`·`NTFY_TOPIC`·
`GOOGLE_OAUTH_*`의 유일한 보관처는 **Railway env**다. 확인은 `railway variables --kv`
(출력 공유 시 마스킹). 로컬 개발은 이 값들 없이도 동작한다 — 외부 연동이 no-op이
될 뿐이다(하드룰 P4).

**실서버(Railway+Vercel, 예전 검증용 데이터 잔존)**
- 백엔드 Railway: https://backend-production-27e5f.up.railway.app
- 프론트 Vercel: https://audio-platform-eta.vercel.app

**본수집 주력 서버는 NAS로 전환됨** (2026-08-26, §3-6 참조)
- 시놀로지 DS925+ (IP 203.247.33.93), Docker Compose 자체 호스팅
- 백엔드: http://203.247.33.93:8100 · 프론트: http://203.247.33.93:3100
- `STORAGE_MODE=local`, ACCESS_TOKEN은 NAS `.env`에 있음(코드/문서에 안 남김)
- 1~4일차 본수집 216개 원본 + 세그먼트 2,137개가 여기에 있다 — **검수·분석은
  이제 이 NAS 주소를 기준으로 한다.**
- **저장소 경로: `/volume1/AURA/01_Projects/01_BeepSound/03_DashBoard`**
  (2026-08-28 기준). 경로가 세 번 바뀌었다 — `audio-platform` →
  `beep_sound_dataset`(§3-8) → `01_BeepSound/03_Experiment`(§3-9) →
  `03_DashBoard`(개명, §5 항목31). 데이터는 형제 폴더 `02_Dataset`,
  원본 녹음은 `01_Raw`에 있다. 상세 구조는 docs/20.
- **SSH 계정: `aura_admin`** (2026-08-28 변경 — 교수님이 기존 관리자
  로그인을 막고 새 계정 발급). `ssh aura_admin@203.247.33.93`.

---

## 3. 지금 하던 일 (다음 세션이 이어받을 것)

### 3-1. 방금 끝낸 것 — 대역 집계 평균 → 최대값 (2026-08-21)

커밋 `385970c` + §11 갱신 `7d8689d`. **로컬 검증까지 완료, 실서버 반영은 안 함.**

탐지기가 타겟 대역(1900~2100Hz)의 프레임별 dB를 **평균**으로 집계하던 것을
**최대값**으로 바꿨다. 코드 변경은 `event_detection.py`의 `.mean(axis=0)` →
`.max(axis=0)` 한 줄.

| 004 GT(정답 31개), 파라미터 동일 | TP | FP | FN | F1 |
|---|---|---|---|---|
| 평균(구) | 24 | 7 | 7 | 77.4% |
| **최대(신)** | **29** | **2** | **2** | **93.5%** |

경보음은 좁은 대역의 순음이라 200Hz 폭 평균은 신호를 이웃 빈에 희석시킨다
(034 실측 5.6dB 손해). 상세·판단 과정·저지른 실수는 **docs/17 §2i**.

### 3-2. 실서버 배포 + 재검증 — **완료** (2026-08-21)

`railway up --detach` (deployment `18fa1504`) → `/health` 200 OK 확인 후,
id=45 "탐지 시험 (본녹음 샘플)"의 dataset 21(260819_034)을
`POST /api/datasets/21/process`로 `replace_existing=true` 재커팅(Job 31).

**결과 — 로컬 검증과 완전 일치**:
- `quality_check`: `expected 10, actual 10, status ok`
- 간격 9.5~10.3초(중앙 10.0초), prominence 23.4~30.6dB
- 48000Hz/4채널/**24bit** 원본 그대로 유지, 파일명 `A1_D0_L1_P0_W1_K1_001~010.wav`

id=42 "beep sound"(실수집처, 목표 2160)는 검증에 쓰지 않았다.

**다음 단계 후보**: 본녹음 나머지(015·024·045·049) 라벨 조건 확보 후 업로드,
또는 `height_db` 기본값 재검토(005 GT 확보 시), 또는 NAS 이전 착수.
사용자 지시 대기.

### 3-3. 보류 중인 판단

| 항목 | 상태 | 재개 조건 |
|---|---|---|
| `height_db` 기본값 | **5.0 유지** | 004 단독으론 3~4가 F1 95.2%로 낫지만 **005 원본이 로컬에 없다**. 정답 하나로 기본값을 바꾸지 않는다(§5 교훈). 005 확보 후 재스윕 |
| **NAS 이전** | **최우선 — 3·4일차 업로드가 Drive 용량 초과로 막혀 강제됨** (§3-6) | 8/25 세션에서 DSM 관리자 권한 없어 Container Manager 접근 불가였음 — **관리자 확보 여부 먼저 확인**. 시놀로지 DS925+ |
| Railway → NAS 데이터 이전 | 미착수 | NAS 기동 확인 후. STORAGE_MODE를 어떻게 바꿀지(Railway 유지+저장소만 NAS? 완전 자체호스팅?) 방향 재확인 필요 |
| 015·024·045·049 검수 | **사람이 검수 화면으로 전수 확인 진행 중** (§3-4) | localhost:3100, 프로젝트 id=6 → dataset id=7. 완료되면 §11 갱신 |
| **1~4일차 검수** | 1·2일차 완료분(dataset 29·30) 검수 미착수 | 3·4일차 업로드 마무리 후 한꺼번에 검수 진행 권장 |

### 3-4. 015·024·045·049 로컬 업로드+커팅 — 완료, 실서버 미반영 (2026-08-21)

라벨 조건 확정: 015(벽O/후방/90°/30m) · 024(벽O/전방/90°/30m) · 045(벽X/전방/180°/30m) ·
049(벽X/전방/90°/10m), 전부 아파트·기둥있음(사용자 확인).

**실서버(`POST /api/uploads`)로 원본을 올리려다 300초 만에 502로 실패** — §5 신규
함정 항목 참조. 사용자 지시("원본을 드라이브에 안 올려도 되니 플랫폼에서만
구현시켜줘")에 따라 **로컬 플랫폼**(`./scripts/dev.sh`, `STORAGE_MODE=local`)에서
정식 API 흐름(업로드→커팅)으로 처리했다.

- 로컬 프로젝트 id=6 "탐지 시험 (본녹음 샘플) - 로컬" 신설(id=45와 동일 설정 복제)
- dataset id=7에 4개 원본 업로드(각 100초, 48kHz/4ch/24bit 원본 유지) 후
  파일별 `common_labels`로 순차 커팅(Dataset당 동시 Job 1개 제약 — 409 확인)

| 파일 | 라벨 코드 | 결과 |
|---|---|---|
| 015 | `A2_D2_L1_P0_W0_K1` | 10/10 ok |
| 024 | `A2_D2_L1_P0_W0_K0` | 10/10 ok |
| 045 | `A4_D2_L1_P0_W1_K0` | 10/10 ok |
| **049** | `A2_D0_L1_P0_W1_K0` | **9/10 shortfall** |

049의 부족은 **새 문제가 아니다** — 049는 1900~2100Hz 대역에 상시 소음이 깔려
경보음 순간 그 대역이 오히려 내려가는 파일로 이미 규명돼 있다(§6 파이프라인
한계 참조, 이전 세션 실측과 동일하게 9개). 검수로 원본을 훑어 놓친 1개를
사람이 확인하는 절차(docs/19)가 정상 대응이다.

### 3-5. 실서버(Drive) 반영 완료 — 파일 분할 우회 (2026-08-21)

사용자가 "google drive말고 railway+vercel로 만들어둔 우리 플랫폼"에 정식
반영을 요청. Railway 300초 타임아웃(§5-14)의 진짜 원인을 재계측한 결과
**Drive 동기 업로드가 아니라 이 컴퓨터의 업로드 회선 속도(실측 ~130KB/s)가
병목**이었다 — 15MB 랜덤 데이터(Drive 저장 대상 아님)만으로도 114초가 걸려
같은 속도가 나왔다. 즉 백엔드 구조를 비동기로 바꿔도 해결 안 됨(클라이언트가
서버로 바이트를 다 보내는 것 자체가 HTTP 요청의 일부라서).

**해결**: 원본을 이벤트가 없는 안전 지점(각 이벤트로부터 최소 2초 이상,
50초 근방)에서 반으로 잘라 각 28~30MB로 낮춘 뒤 업로드(반쪽당 158~209초,
300초 안에 성공). 로컬에서 먼저 분할·재커팅해 검출 개수가 원본과
정확히 일치함(손실 없음)을 확인한 뒤 실서버에 반영.

**결과** (dataset 21, project 45):

| 파일 | 코드 | 조각 수 |
|---|---|---|
| 034 | A1_D0_L1_P0_W1_K1 | 10 |
| 015 | A2_D2_L1_P0_W0_K1 | 10 |
| 024 | A2_D2_L1_P0_W0_K0 | 10 |
| 045 | A4_D2_L1_P0_W1_K0 | 10 |
| 049 | A2_D0_L1_P0_W1_K0 | **9**(로컬과 동일, 기존 규명 현상) |

로컬(프로젝트 id=6, dataset 7)에도 같은 결과가 남아 있음 — 검수는 실서버
쪽(정식 배포본)에서 진행.

**정리(2026-08-21)**: dataset 21이 034 하나만 담을 목적("260819_034")이었는데
5개 파일이 섞여 이름과 실제 내용이 안 맞았다. 이름 변경 API가 없어서
**PATCH `/api/datasets/{id}` 신설**(docs/06 §4.1b, 커밋 `8bfd101`) 후
"본녹음 샘플 (034·015·024·045·049)"로 재명명. 동시에 프로젝트 45 안에
어제(8/20) **잘못된 라벨**(pillar 값 틀림)로 커팅됐던 dataset 26(024)과
빈 dataset 27(015)·28(049)을 발견해 전부 삭제 — 정상 데이터는 dataset 21
하나에만 있다. 프로젝트 45는 이제 dataset 1개(21)만 남았다.

**다음에 할 일**: **사람이 검수 화면으로 49개 전부 확인**(2026-08-21, 사용자
결정 — 정확도 우선). 049는 놓친 1개가 있으니 원본 파형까지 훑을 것.
검수는 https://audio-platform-eta.vercel.app 프로젝트 45 → dataset 21에서
docs/19 절차대로.

> **NAS 방침 전환**: "다음 주부터 NAS에 업로드 예정이라 Drive에 올릴
> 필요 없어졌다"(사용자, 이후 "지금은 Railway+Vercel 플랫폼에 반영해달라"로
> 정정 — 이번 4개는 실서버에 이미 반영 완료). 앞으로 새 원본 업로드 경로가
> Drive(Railway)에서 NAS로 바뀔 예정이다. §5-14의 Railway 300초 타임아웃은
> NAS 전환으로 우회될 가능성이 높지만(로컬 네트워크라 별도 에지 프록시
> 타임아웃이 없을 수 있음), **NAS 컨테이너 기동이 아직 미검증**이므로
> 실제로 그런지는 NAS 설치 후 확인해야 한다. §3-3의 NAS 이전이 다음
> 우선순위다.

### 3-6. NAS 자체 호스팅 전환 + 1~4일차 본수집 전체 통합 — **완료** (2026-08-26)

Drive 용량 초과(구 기록은 git 이력 참조)로 Railway+Drive 업로드가 막혀
시놀로지 NAS(DS925+, `docs/20`) 자체 호스팅으로 전환, Docker Compose 3개
컨테이너(db/backend/frontend)를 NAS에서 직접 기동했다. `STORAGE_MODE=local`
— Railway는 그대로 유지하되 본수집 데이터는 전량 NAS로 옮겼다(Railway+Drive
대체가 아니라 병행).

1~4일차 원본 216개(각 54개, mic1/mic2 합산) 전부를 NAS에 재업로드하고
`event_detection` 방식(당시 nperseg=2048)으로 커팅해 통합했다.

**최종 상태(2026-08-26, NAS)**:

| dataset | 이름 | 원본 | 세그먼트(nperseg=4096 재커팅 후) |
|---|---|---|---|
| 1 | 1일차 | 54/54 | 532 |
| 2 | 2일차 | 54/54 | 539 |
| 3 | 3일차 | 54/54 | 540 |
| 4 | 4일차 | 54/54 | 526 |

합계 원본 216개, 세그먼트 2,137개, 실패 0건.

### 3-7. nperseg=4096 전체 재커팅 — **완료** (2026-08-26)

018·029번(3일차, 각각 인접 이벤트 병합·약한 배경 오탐 사례 — docs/17 §2j)으로
nperseg=2048→4096을 검증 채택한 뒤, NAS의 1~4일차 216개 원본 전체를
`replace_existing=true`로 일괄 재커팅했다.

**028번 파일명 충돌 실패 → 원인 규명 → 해결**:
018·029를 제외한 214개를 순서대로 재처리하던 중 `260820_028.WAV` 1건만
`파일명 충돌: segments/3/A2_D0_L1_P1_W1_K1_526.wav 가 이미 존재합니다`로
실패했다. 원인은 **028과 029가 mapping.py상 완전히 동일한 라벨 코드**
(`A2_D0_L1_P1_W1_K1` — 같은 각도·거리·설치조건 반복 촬영)를 갖는데, seq가
dataset 전역 누적(`count_by_dataset + 1`, worker.py:154)이라 **029를 먼저
별도 Job으로 재커팅해 524~533을 다 쓴 뒤 028을 또 다른 Job으로 재처리**하면
반드시 그 사이 어딘가에서 번호가 겹친다(028을 재시도해도 531에서 재충돌 —
어느 순서로 해도 재발하는 구조적 문제). **해결**: 028·029를 **하나의 Job**
(`source_file_ids: [137, 138]`)으로 함께 재커팅 — 같은 Job 안에서 seq가
순서대로 배정돼 충돌 없이 완료(각 10/10). 상세는 docs/17 §2k. **교훈**: 라벨
코드가 같은 원본들의 부분 재처리는 반드시 같은 Job으로 묶을 것.

**최종 통계**: 216/216 원본, 세그먼트 2,137개, 실패 0건(위 표 참조).

**다음 세션이 할 일**:
1. 1~4일차 NAS 데이터 사람 검수(docs/19 절차, 프론트 http://203.247.33.93:3100)
2. 시각화 갤러리(Artifact) 재생성 필요 시 진행 — 이전 세션에서 요청받았던
   NAS 링크 기준 1~4일차 갱신은 아직 미착수
3. 로컬(id=6)·Railway 실서버(project 41/42/45)에 남은 검증용 데이터 정리 여부 확인
4. mapping.py의 DAY3_MIC1[24]·DAY4_MIC1(32~61 오프셋 규칙)은 이미 검증
   완료 — 재사용 가능

### 3-8. audio-platform → beep_sound_dataset 폴더 통합 — **완료** (2026-08-27)

교수님 지시: "beep_sound_dataset 폴더 하나에 녹음본·업로드본·세그먼트 다
들어가게 하고, audio-platform 폴더는 삭제"(연구원 tykim23·bbkim23이
이미 원본 mic1·mic2를 올려둔 폴더와 플랫폼을 하나로 합침).

**조사로 밝혀진 사전 상태**: `beep_sound_dataset/segments/`에 이미
플랫폼 데이터와 100% 동일한 사본이 존재했다(`diff -rq`로 확인, 파일
개수·크기·mtime 전부 일치) — `_dataset_info.txt`(어제 배포한 안내파일
기능의 산물)까지 포함돼 있어, 연구원이 최근(8/26~27) `audio-platform/data`를
미리 복사해둔 것으로 판단. 두 볼륨은 서로 다른 btrfs subvolume(inode도
다름)이라 심볼릭 링크가 아니라 완전 별도의 물리적 복사본이었다. 실제
컨테이너가 마운트하는 곳(`docker inspect`로 확인)은 여전히
`audio-platform/data`였다.

**이전 절차**:
1. 백업: 코드(`tar.gz`, db 폴더 제외) + DB(`pg_dump`) → `/volume1/backups/`
2. `sudo docker compose down`
3. `audio-platform/data/uploads` → `beep_sound_dataset/uploads` 이동
4. `beep_sound_dataset/segments`(사본)를 지우고 `audio-platform/data/segments`
   (진짜)를 이동 — 사본이 아닌 원본을 남기는 원칙
5. 코드·설정·DB(`backend`·`frontend`·`.env`·`compose.yaml`·`db`·`.git`
   등 전부) 이동. **`db` 폴더는 소유자가 postgres uid(70)라 일반 계정
   `mv`가 실패 — `sudo mv` 필요**했다.
6. `compose.yaml`의 볼륨 마운트를 `./data:/data` 하나에서
   `./uploads:/data/uploads`·`./segments:/data/segments`·
   `./exports:/data/exports` 개별 마운트로 변경(mic1·mic2·backend를
   컨테이너에 노출하지 않기 위해) — 로컬 `docker-compose.nas.yml` 커밋
   `682afef` 후 scp로 NAS에 전송
7. `beep_sound_dataset`에서 `sudo docker compose up -d --build`
   — **`exports` 폴더가 없어서 첫 시도는
   `Bind mount failed: '.../exports' does not exist`로 실패**, `mkdir -p
   exports` 후 재시도해 성공
8. 전수 검증: 8개 dataset 전부 세그먼트 개수 이전과 정확히 일치(1:532,
   2:539, 3:540, 4:526, 5~8:540), 각 dataset 대표 파일 waveform API
   전부 200 OK 확인
9. 검증 통과 후 `audio-platform` 폴더 전체 삭제(`sudo rm -rf`)

**부수 발견 — dataset 삭제 시 잔재 남는 버그**: 검증용으로 만들었던
dataset 9·10을 API로 삭제(204 확인)했는데도 `uploads/10`·`segments/10`
폴더와 그 안의 `_dataset_info.txt`가 파일시스템에 그대로 남아있었다.
`DatasetService.collect_storage_paths()`가 세그먼트·원본·export 파일만
모으고 `_dataset_info.txt`(안내파일 기능, 커밋 `12cd98d`)는 목록에
없어서 삭제 대상에서 빠진 것 — **같은 날 수정 완료**(`a0c25b7`,
`collect_storage_paths`에 안내파일 경로 추가 + `get_or_create_default`
경로에도 안내파일 생성 누락돼 있던 것 함께 수정, §3-10 참고).

**1차 통합 구조**(이후 §3-9에서 다시 3분할로 재이전됨): 당시엔
`/volume1/beep_sound_dataset/`에 `mic1`·`mic2`(원본, 연구원 직접
관리)·`uploads`·`segments`·`exports`(플랫폼 데이터)·`backend`·
`frontend`·`db`·`.env`·`compose.yaml` 등 전부 통합했었다.

### 3-9. beep_sound_dataset → 01_BeepSound 3분할 재이전 — **완료** (2026-08-27, 같은 날)

교수님이 §3-8 직후 다시 지시: "beep_sound_dataset도 없애고, AURA →
01_Projects → 01_BeepSound에 들어가게 하라"— 이 폴더 안에 이미
`01_Raw`·`02_Dataset`·`03_Experiment` 3개 하위 폴더가 준비돼 있었다.

**배치 결정**(사용자 확정):
- `01_Raw` ← `mic1/`, `mic2/` (녹음 원본)
- `02_Dataset` ← `uploads/`, `segments/`, `exports/` (플랫폼이 관리하는
  업로드본·커팅 조각·CSV — "정제된 데이터셋 산출물")
- `03_Experiment` ← `backend/`, `frontend/`, `db/`, `.env`,
  `compose.yaml` 등 플랫폼 코드+DB 전체 ("실험을 굴리는 도구/환경")

**경로 확인 함정**: `01_BeepSound`가 실제로 두 경로에 다 보였다 —
`/volume1/AURA/01_Projects/01_BeepSound`(일반 사용자 경로)와
`/volume1/@appdata/ContainerManager/all_shares/AURA/01_Projects/
01_BeepSound`(Container Manager 경로). `ls -di`로 inode를 비교해 완전히
같은 물리 위치(bind mount)임을 확인 — §3-8의 `beep_sound_dataset`도
같은 패턴이었다. **compose.yaml의 볼륨 마운트는 Container Manager
경로를 기준으로 삼는다**(사용자 결정, Docker가 더 안정적으로 인식).

**compose.yaml은 03_Experiment 안, 데이터는 형제 폴더 02_Dataset에** —
상대경로(`./uploads`)로는 더 이상 안 닿으므로 절대경로로 바꿨다.
다음에 또 구조가 바뀔 걸 대비해 `${DATASET_DIR:-절대경로기본값}`
환경변수로 오버라이드 가능하게 했다(`.env`에 `DATASET_DIR=...`만
추가하면 코드 수정 없이 이전 가능) — 커밋 `d9805dd`.

**절차**: 코드 백업(tar.gz, `db`·데이터 폴더 제외) + DB 덤프
(`audio_platform_db_20260827_v2.sql`) → `docker compose down` →
`01_Raw`·`02_Dataset`·`03_Experiment`로 각각 이동(`db`는 §3-8과 같이
소유권 때문에 `sudo mv` 필요) → compose.yaml 수정·전송(맥 새 터미널
scp, `grep`으로 반영 확인) → `03_Experiment`에서 `sudo docker compose
up -d --build`(컨테이너 이름이 `03_experiment-*`로 자동 변경됨) →
8개 dataset 전수 검증(세그먼트 개수 일치, waveform 200) → 
`beep_sound_dataset` 폴더 삭제.

**최종 구조**: `/volume1/AURA/01_Projects/01_BeepSound/
{01_Raw,02_Dataset,03_Experiment}`. 상세는 docs/20(갱신 완료).

### 3-10. dataset 삭제 시 안내파일 잔재 버그 수정 — **완료** (2026-08-27)

§3-7에서 발견한 버그(`_dataset_info.txt`가 dataset 삭제 시 파일시스템에
안 지워짐)를 커밋 `a0c25b7`로 수정. `DatasetService.
collect_storage_paths()`에 안내파일 경로 2개(`uploads/{id}/
_dataset_info.txt`, `segments/{id}/_dataset_info.txt`)를 추가했고,
업로드 시 자동 생성되는 기본 dataset 경로(`get_or_create_default()`)
에도 안내파일 생성이 원래 빠져 있어 `storage` 파라미터를 추가해 통일.
테스트(`test_delete_api.py`)에 안내파일 생성·삭제 검증 추가, 전체
231개 테스트 통과 확인. **NAS 배포·재현 검증까지 완료**(생성→삭제→
잔재 없음 확인).

### 3-11. 비프 대역 확대 탭 + 대역통과 검출기 — **완료·NAS 배포** (2026-08-28)

사용자 요청으로 기존 기능을 일절 건드리지 않고 **표시 전용 신규 기능**
2가지를 추가했다(설계는 docs/16 §7, 커밋 `5d54e88`·`f47a0f8`).

**왜**: 차량 비프음(차키 리모컨, 1900~2100Hz 협대역)이 저역 배경(엔진·
환기팬·음악)에 묻혀, 기존 전대역 파형의 "평균+2.5σ" 피크 검출은 문
닫힘·차량 통과 같은 광대역 충격음만 잡고 정작 비프음을 놓쳤다. 기존
스펙트로그램도 100Hz~16kHz를 한 화면에 그려 관심 대역이 몇 픽셀뿐이라
육안 확인이 불가능했다.

**무엇을**: ① `band_beep_detector.py`(대역통과 filtfilt → Hilbert
엔벨로프 → 지역 median+k·MAD + 전역 하한 → find_peaks) ②
`band_spectrogram.py`(선형 STFT를 1500~2500Hz만 크롭) ③
`verify_onsets.py`(오프셋 통계) ④ `SourceBandSpectrogram.tsx`(세 번째
탭). 기존 파일은 연결 코드만 최소 수정.

**실측으로 사양을 두 번 고쳤다**:
- `k` 기본값: 사양 5 → **8**. k=5는 합성 신호에서 오탐 25개.
- **경계 오탐 결함 발견·수정**: 실제 NAS 세그먼트로 돌려보니 파일
  맨앞·맨끝에서 오탐이 났다. 원인은 `median_filter(mode="nearest")`가
  경계에서 값을 복제해 **지역 MAD가 거의 0**이 되는 것(실측 0.0000007,
  진짜 onset의 1/25). k를 올려도 안 고쳐지고 오히려 진짜 신호를 놓쳤다.
  전역 하한(`k_global=8`)을 함께 걸어 해결.

**오탐 문제와 해결(같은 날, 사용자 지적 후)**: 처음 배포본은 실데이터
100초에서 **20개**(진짜 10 + 오탐 10)를 잡았다. 사용자가 "피크 후보가
상관없는 곳에 찍힌다"고 지적해 원인을 실측했다.

원본 wav를 받는 API가 없어서 **fixed_interval 세그먼트 10개를 이어붙여
100초 원본을 복원**한 뒤(이 방법을 기억할 것 — event_detection 세그먼트
6초짜리로는 오탐 지점이 안 잘려 있어 분석 불가), 진짜와 오탐의 스펙트럼을
직접 비교했다:

| | 피크 주파수 | 대역 안/밖 에너지 비 |
|---|---|---|
| 진짜 10개 | **전부 1992Hz** | 14.9~19.3 dB |
| 오탐 10개 | 1922~2086Hz 흩어짐 | 2.0~11.8 dB |

겹치는 구간이 없어 **순음성(tonality) 필터**를 추가했다(`tonality_db=14`,
실제 구현으로 스윕해 결정 — 12~13은 오탐 잔존, 16부터 진짜를 놓침).
동시에 **기존 파형의 ▲도 새 검출기 결과로 교체**했다(전대역 평균+2.5σ는
저역 소음에 반응해 문 닫힘·차량 통과만 찍혔다).

**최종 NAS 검증**(`260818_001.WAV`): 검출 **10개·오탐 0**, 오프셋
5.62~5.92초(표준편차 **0.08초**), 간격 9.80~10.14초 — 화면에 "규칙적 —
검출 정상으로 보임". 파형 ▲와 비프 대역 탭 빨간선이 같은 지점을 가리킨다.

**중요한 부수 관찰**: NAS 실데이터의 실제 비프음 위상이 **5.85초**다
(사양은 "초의 일의 자리 5초"). 일관되게 0.85초 늦으므로 녹음 시작
지연으로 보인다 — **위상 GT를 쓸 때 "5.0초 고정"이 아니라 파일별
오프셋 중앙값 기준으로 판단해야 한다.**

---

## 4. 서버 현재 상태 (2026-08-28)

**NAS (본수집 주력, http://203.247.33.93:8100)**

| dataset | 이름 | 원본 | 세그먼트 | 커팅 파라미터 |
|---|---|---|---|---|
| 1 | 1일차 | 54/54 | 532 | event_detection, nperseg=4096 |
| 2 | 2일차 | 54/54 | 539 | event_detection, nperseg=4096 |
| 3 | 3일차 | 54/54 | 540 | event_detection, nperseg=4096 |
| 4 | 4일차 | 54/54 | 526 | event_detection, nperseg=4096 |

같은 NAS에 `fixed_interval`(10초 고정) 버전 프로젝트 `beep_sound_dataset`도
별도로 존재 — 원본당 정확히 10개씩, 216개 원본 × 10 = 2,160 세그먼트.

**Railway+Vercel (예전 검증용 데이터, 정리 여부 미확인 — §3-7 다음 할 일)**

| id | 프로젝트 | 커팅 파라미터 | 내용 |
|---|---|---|---|
| 41 | 경보음 탐지(파일럿 검증) | height=5 / gap=4 | 파일럿 004·005 |
| 42 | **beep sound** | height=3.0 / gap=8.0 | 목표 2160 — NAS 전환 전 부분 업로드 잔존(1·2일차 완료, 3일차 부분, 4일차 미착수) |
| 45 | 탐지 시험 (본녹음 샘플) | height=3.0 / gap=8.0 | dataset 21 "본녹음 샘플 (034·015·024·045·049)" — 49개 세그먼트 |

전부 `cutting_mode=event_detection`. 운용 파라미터가 코드 기본값(height 5.0/gap 4.0)과
다른 것은 정상이다 — **도메인 값은 Project 설정에서 온다**(하드룰 P1).

**실서버 검증 관례**: 임시 리소스는 이름에 `(삭제예정)`을 붙이고 끝나면 반드시
DELETE + Notion 페이지도 아카이브. **실데이터 프로젝트를 검증에 쓰지 않는다.**

---

## 5. 이 프로젝트에서 실제로 데인 것들 (반복 금지)

전역·프로젝트 규칙은 `~/.claude/CLAUDE.md`와 `CLAUDE.md`에 있다. 여기엔 **문서만
읽어선 안 보이는 것**을 남긴다.

### 판단·검증

1. **불공정 비교로 결론내지 말 것.** 평균 vs 최대를 파라미터가 다른 상태로
   비교해 정반대 결론을 냈다. **변수 하나만** 바꿔 비교한다.
2. **가진 정답부터 쓸 것.** 004 GT를 한 번만 돌렸으면 F1 16%p 차이가 바로
   보였는데, 정답이 일부뿐인 본녹음으로 한참 씨름했다.
3. **정답의 정밀도를 확인하고 쓸 것.** 사용자가 귀로 들은 "88초쯤"을 0.1초
   정밀 GT처럼 채점에 써서 잘못된 쪽을 편들었다.
4. **테스트가 통과한다고 테스트가 옳은 건 아니다.** 합성 배경의 64탭 이동평균이
   2000Hz에 널을 만들어 **심어둔 이벤트 상승분이 −8.4dB(음수)** 였는데도, 배경
   오탐이 우연히 정답 위치 1.5초 안에 떨어져 통과하고 있었다.
5. **실패 원인을 "방식의 한계"로 일반화하기 전에 구현 선택지를 의심할 것.**
   docs/17에서 **두 번** 같은 실수를 했다 — §2c(구간 병합 결함을 알고리즘 탓으로)
   와 §2g(집계 방식 문제를 접근법 한계로).
6. **숫자만 보고 "된다"고 하지 말 것.** "31개 검출, 5/5 적중"이라 보고했다가
   실제로는 TP24/FP7/FN7이었다. 소리는 들어봐야 한다.
7. **검증 안 한 기능을 슬쩍 넣지 말 것.** "주기 재탐색"을 GT 검증 없이 추가했다가
   사용자 지적으로 전부 제거했다(docs/17 §2e).

### 기술적 함정

8. **배경 오탐은 정상이다.** 034의 이벤트 없는 구간에서도 baseline diff가 최대
   15.2dB까지 튄다(p95 5.5dB). 테스트는 "오탐 0"이 아니라 **"심어둔 이벤트를
   찾는가"**를 검증해야 한다.
9. **저장소 루트에 큰 오디오 파일을 두지 말 것.** `railway up`이 반복 timeout
   난다. 루트 `.dockerignore`는 지우지 말 것 (실사고 `2e36f00`).
10. **dev 서버 켜둔 채 `npm run build` 금지** — `.next`가 깨져 간헐적 500.
11. **HTTP 헤더에 한글**은 RFC 5987(`filename*=UTF-8''...`). 원시 한글은 500.
12. **curl로 한글 쿼리 파라미터**는 `-G --data-urlencode` (미인코딩은 400).
13. **커팅 조각은 원본 비트깊이를 유지**해야 한다. `write_wav` 기본값이 PCM_16이라
    24bit 원본이 강등되던 버그가 있었다(`bcb0d2b`, `SegmentAudio.subtype`).
14. **Railway 에지 프록시가 요청당 300초 하드 타임아웃을 건다** — 앱/`MAX_UPLOAD_MB`와
    무관하게 300초에서 502로 끊긴다(응답 바디 없음, 앱 로그에 요청 자체가 안 찍힘).
    **처음엔 Drive 동기 업로드가 원인이라 추정했으나 재계측으로 틀렸음을 확인** —
    Drive 저장 대상이 아닌 순수 랜덤 데이터 15MB만으로도 114초가 걸려 같은 속도
    (~130KB/s)가 나왔다. **진짜 병목은 클라이언트(이 컴퓨터)의 업로드 회선
    속도다.** 클라이언트→Railway 전송 자체가 HTTP 요청의 일부이므로, 백엔드를
    비동기(백그라운드 Job)로 바꿔도 이 구간은 줄지 않는다 — 서버가 요청을 다
    받아야 코드가 실행되기 때문. 300초 안에 보낼 수 있는 크기는 이 회선 기준
    약 35~39MB. **10분 이상 녹음(대략 50MB+)은 통짜로 업로드하면 실패한다.**
    확정된 우회책: **이벤트가 없는 안전 지점에서 원본을 잘라 나눠 올린 뒤
    서버에서 각각 커팅**(§3-5에서 실제 적용, 원본과 검출 결과 손실 없이 일치
    확인됨). 회선이 개선되거나 NAS로 전환되면 이 문제 자체가 없어질 수 있다.
    2026-08-21 015/024/045/049 업로드 시도로 발견 — §3-4·§3-5 참조.

15. **`DELETE /api/datasets/{id}`로 지운 dataset id는 재사용할 수 없다.**
    삭제 후 같은 id로 재업로드를 시도하면 전부 `404 Dataset을 찾을 수
    없습니다`로 거부된다. 재작업할 땐 새로 생성된 dataset의 **새 id**를
    다시 조회해서 스크립트에 반영해야 한다(project의 dataset 목록 API로
    확인). 2026-08-26 1·2일차 재업로드 때 겪음 — dataset 22·23을 지우고
    22·23으로 재시도해 전량 실패, 실제로는 29·30이 새로 생겼었다.

16. **Drive 403의 정확한 사유가 서버 로그에 안 남는다.** `storage/drive.py`의
    `_request()`가 `res.raise_for_status()`만 호출해서, Google이 반환한
    에러 본문(`storageQuotaExceeded` 등 원인 코드)이 스택 트레이스에서
    사라진다. 남는 건 `403 Forbidden` 상태 코드뿐 — 용량 초과인지 권한
    문제인지 API 비활성화인지 로그만 봐서는 구분 불가. 2026-08-26 3·4일차
    업로드가 이 상태로 막혀 원인을 정황(docs/20의 "Drive 14GB 부족" 기록 +
    당일 업로드량 역산)으로만 추정했다 — **다음에 같은 걸 겪으면
    `_request()`에서 실패 시 `res.text`를 로그에 남기도록 먼저 고칠 것.**

17. **NAS의 scp가 구버전 SCP 프로토콜을 거부한다.** `subsystem request
    failed` / `Connection closed`로 실패 — `scp -O`(대문자 O, SFTP 강제)
    옵션을 붙여야 한다. **반드시 맥(로컬) 터미널에서 실행할 것** — NAS SSH
    세션 안에서 `scp -O`를 실행하면 NAS 쪽 구버전 scp가 `-O` 자체를
    모르는 옵션으로 거부한다(`unknown option -- O`). 어느 쪽 터미널인지
    헷갈리기 쉬우니 프롬프트를 확인할 것.

18. **macOS 리소스 포크 파일(`._*`)이 tar 전송에 딸려가면 alembic이 깨진다.**
    `.py` 확장자를 가진 `._xxx.py` 리소스 포크 파일을 alembic이 마이그레이션
    스크립트로 읽으려다 `SyntaxError: source code string cannot contain
    null bytes`로 실패한다. `find <경로> -name "._*" -delete`로 정리 후
    재빌드. tar로 옮기기 전에 `COPYFILE_DISABLE=1 tar ...`로 애초에
    안 만드는 게 더 안전하다.

19. **pydantic-settings의 `list[str]` 환경변수는 JSON 배열 형식이어야 한다.**
    `CORS_ORIGINS=http://x`처럼 일반 문자열로 넣으면
    `error parsing value for field "cors_origins"`. `CORS_ORIGINS=["http://x"]`
    형식으로 넣을 것.

20. **Docker Compose `.env` 변경은 `restart`로 반영 안 된다.** 컨테이너를
    껐다 켜는 것만으로는 env가 새로 안 읽힌다 — `docker compose up -d
    --force-recreate` (이미지도 바뀌었으면 `--build`까지) 필요.
    `docker exec <container> env | grep KEY`로 실제 반영 여부를 직접
    확인하는 습관을 들일 것 — "파일은 고쳤다"와 "컨테이너에 반영됐다"는
    별개다. 2026-08-26 nperseg 값 반영 때 이 확인을 생략해 한 번 헛빌드했다.

21. **`docker compose`는 `.env`를 실행 디렉터리 기준으로 찾는다** (compose
    파일 경로를 `-f`로 지정해도 무관). `.env`가 없거나 다른 폴더에 있으면
    `required variable DB_PASSWORD is missing` 같은 에러가 나는데, 원인이
    "env가 없다"가 아니라 "다른 데서 찾고 있다"인 경우가 있으니 `pwd`부터
    확인할 것.

22. **`frontend/public/` 폴더가 저장소에 아예 없으면 Docker 빌드가
    `"/app/public": not found`로 실패한다** (`Dockerfile`의
    `COPY --from=builder /app/public ./public`). Next.js는 이 폴더가
    없어도 로컬 `npm run dev`/`next build`는 통과하므로 평소엔 안 드러난다.
    `frontend/public/.gitkeep`으로 폴더 자체를 저장소에 커밋해 둘 것
    (커밋 `2015798`).

23. **dataset 전역 seq 카운터(A1, docs/12)와 "라벨 코드가 동일한 원본들의
    부분 재처리"가 만나면 파일명이 충돌한다.** `count_by_dataset + 1`로
    seq를 매기므로, 같은 라벨 코드를 가진 원본 여럿을 **각각 별도 Job**으로
    `replace_existing=true` 재처리하면 어느 쪽을 먼저 하든 번호가 겹친다.
    반드시 그 원본들을 **하나의 Job**(`source_file_ids`에 함께 나열)으로
    묶어서 재처리할 것. 상세 사례는 docs/17 §2k.

24. **NAS `data/uploads/{id}`·`data/segments/{id}` 폴더명을 File Station에서
    직접 rename하면 DB의 `storage_path`(숫자 경로 그대로)와 어긋나
    `waveform`/`spectrogram` API가 전부 500이 난다** (`soundfile.
    LibsndfileError: ... System error` — 실제로는 파일을 못 찾는 것).
    `sources` 같은 DB 전용 조회는 영향이 없어 원인 특정이 늦어진다.
    **해결됨(2026-08-27, 커밋 `12cd98d`)**: 폴더명은 숫자 그대로 두고,
    dataset 생성·이름변경 시 폴더 안에 `_dataset_info.txt` 안내 파일을
    자동 생성하도록 코드를 고쳤다 — File Station에서 폴더를 열면 무엇인지
    바로 보이므로 **다시 폴더명을 직접 바꿀 필요가 없다.** 기존 NAS
    dataset 1~8에도 소급 적용 완료. 상세는 docs/17 §2l.
    **NAS 배포 시 주의**: git이 NAS에 없어 scp로 개별 파일을 보내야 하고,
    scp는 반드시 **맥의 새 터미널**(NAS SSH 세션이 아닌 곳)에서
    `scp -O <로컬경로> <계정>@203.247.33.93:<NAS경로>` 형태로 실행해야
    한다 — NAS 세션 안에서 실행하면 `-O`를 모르는 구버전 scp라 실패한다.
    전송 후에도 "완료됐다"는 말만 믿지 말고 **`ls -la`로 NAS 파일의
    mtime이 실제로 바뀌었는지, `grep`으로 새 코드 문자열이 들어있는지**
    직접 확인할 것 — 이번에도 처음엔 옛 파일 그대로였다.

25. **`dataset` API로 삭제해도 `_dataset_info.txt`와 빈 uploads/segments
    폴더가 파일시스템에 남는다(미수정 버그).** `DatasetService.
    collect_storage_paths()`가 세그먼트·원본·export 파일 경로만 모으고
    안내파일(커밋 `12cd98d`)은 대상에 없어서다. 검증용 dataset을
    만들었다 지웠는데 다음 dataset 개수 세기(`ls | wc -l`)가 예상보다
    많이 나오면 이 잔재를 의심할 것 — 2026-08-27 beep_sound_dataset
    이전 중 dataset 10 잔재로 실제로 겪었다(수동으로 `rm -rf` 정리).
    다음 세션에서 `collect_storage_paths`에 `_dataset_info.txt` 경로도
    포함하도록 고칠 것.

26. **NAS의 `db/` 폴더(PostgreSQL 데이터 디렉터리)는 소유자가 postgres
    컨테이너 내부 uid(70)라 일반 계정 `mv`가 `Permission denied`로
    실패한다.** `sudo mv`를 써야 한다. `docker compose down`으로
    컨테이너를 내린 상태에서만 옮길 것(떠 있는 채로 옮기면 DB 파일
    손상 위험).

27. **`compose.yaml`이 개별 폴더를 bind mount(`./uploads:/data/uploads`
    등)로 참조하면, 그 폴더가 미리 존재해야 `docker compose up`이
    성공한다** — 없으면 `Bind mount failed: '...' does not exist`로
    기동 자체가 실패한다(단일 마운트 `./data:/data`였을 때는 하위
    폴더가 없어도 상위 `data`만 있으면 됐던 것과 다른 점). CSV export를
    한 번도 안 돌린 새 배치에서는 `exports/` 폴더가 아예 없을 수
    있으니, 이런 구조로 옮길 땐 대상 폴더들을 `mkdir -p`로 미리
    만들어 둘 것.

28. **NAS의 일반 계정은 `/volume1` 최상위에 새 폴더를 만들 권한이
    없다** (`mkdir: cannot create directory '/volume1/backups':
    Permission denied`) — `sudo mkdir` + `sudo chmod`로 우회.

29. **시놀로지 공유 폴더는 두 가지 경로로 동시에 보인다** —
    `/volume1/<공유폴더명>/...`(일반 사용자 경로)와
    `/volume1/@appdata/ContainerManager/all_shares/<공유폴더명>/...`
    (Container Manager 경로) — `ls -di`로 inode를 비교하면 완전히 같은
    물리 위치(bind mount)임을 확인할 수 있다. **Docker Compose 볼륨
    마운트는 Container Manager 경로를 쓰는 게 더 안정적**이다(2026-08-27
    확정 관례). `docker compose` 볼륨의 상대경로(`./x`)는 compose.yaml
    파일이 있는 위치 기준이므로, **코드와 데이터가 다른 폴더에 있으면
    반드시 절대경로로 바꿔야 한다** — 상대경로를 그대로 두면 엉뚱한
    곳에 빈 폴더가 새로 생기거나 `Bind mount failed`가 난다.

30. **NAS 저장소 경로가 짧은 시간에 반복해서 바뀔 수 있다** (실제로
    하루 만에 두 번: `audio-platform`→`beep_sound_dataset`→
    `01_BeepSound/03_Experiment`). 매번 compose.yaml을 손으로 고치는
    대신 **`${DATASET_DIR:-기본경로}` 같은 환경변수 오버라이드**를 넣어
    두면, 다음 이전은 `.env`에 한 줄 추가하는 것만으로 끝난다(코드
    수정·커밋·scp 재전송 불필요) — docs/17·21처럼 반복될 걸 알면서도
    매번 문서만 고치는 대신, 이런 구조적 대비를 해두는 게 다음 세션의
    시간을 아낀다. **실제로 하루 뒤 또 바뀌었다**(항목31) — 이 대비
    덕분에 compose.yaml은 안 고쳐도 됐다.

31. **폴더명·계정이 예고 없이 바뀔 수 있다** (2026-08-28 실제 발생):
    `03_Experiment` → **`03_DashBoard`**, 계정 `AURA` → **`aura_admin`**
    (교수님이 기존 관리자 로그인을 막고 새 계정 발급). 배포하려다
    `scp: No such file or directory`가 나면 **경로가 아직 그대로인지부터
    확인**할 것 — NAS에 SSH로 붙어 `ls -la /volume1/AURA/01_Projects/
    01_BeepSound/`를 보면 바로 드러난다. 함께 겪은 것들:
    - **`scp -O`는 대상에 파일명까지 써야 한다.** 디렉터리로 끝나면
      `Is a directory` 에러(`.../03_DashBoard/` ❌ →
      `.../03_DashBoard/파일.tar.gz` ✅).
    - **폴더명이 바뀌면 compose 프로젝트명도 바뀐다**(컨테이너가
      `<폴더명 소문자>-<서비스>-1`). 개명 후 `docker compose ps`가
      **빈 목록**을 보여주지만 서비스는 옛 이름으로 살아있다 —
      `sudo docker ps`로 확인하고, 정리는 `sudo docker compose
      -p 03_experiment down` 처럼 **옛 프로젝트명을 명시**한 뒤
      `up -d --build`로 새로 올린다. DB(`./db`)는 유지되므로 데이터는
      안 날아간다(실측: 8개 dataset 세그먼트 수 전부 일치).
    - 파일 여러 개를 보낼 땐 `COPYFILE_DISABLE=1 tar -czf`로 묶어
      한 번에 보내는 게 편하다(macOS `._*` 리소스 포크 방지, 항목18).

---

## 6. 비프음 탐지 파이프라인 (현재 연구 주제)

> 상세는 **docs/17**. 여기선 이어받는 데 필요한 것만.

```
채널 평균(mean) → 리샘플 48k→44.1k → STFT(2048/1024)
→ 대역(1900~2100Hz) dB의 **최대값**        ← 2026-08-21 평균에서 변경
→ baseline diff(앞뒤 25프레임 median, 자기 제외)
→ find_peaks(height, distance) → **원본에서** [탐지-3초, 탐지+3초] 커팅
```

**절대 어기면 안 되는 제약 (사용자 명시)**
- **노이즈 제거(밴드패스·스펙트럴 게이팅 등 신호 변형) 금지.** 판단(탐지)에만
  가공 신호를 쓰고, **커팅은 항상 원본에서** 한다. 테스트로 고정돼 있다.
- **정량 평가 문제로 다룬다.** "잘 찾는 것 같다"가 아니라 GT 대비 TP/FP/FN으로
  판단한다. 새 파라미터·로직은 **수치 확인 후** 채택하고, 개선 없으면 코드에
  넣지 말고 **실험 기록으로만** 남긴다(docs/17에 기각 기록 5건).

**평가 도구** (탐지기와 동급 우선순위 — 사용자 요구사항)
```bash
cd backend
uv run python scripts/evaluate_detection.py \
  --audio <원본.WAV> --gt gt/pilot_004.json \
  --sweep height_db=3,4,5,6 --detail
```
`backend/gt/*.json`에 GT를 넣으면 자동으로 평가 대상이 된다. 새 파일은
**JSON 하나만 추가**하면 된다.

**성능 한계 (정직하게)**: 청취 확인 결과 오탐(84.2초)이 진짜 경보음(87초)보다
신호가 강한 사례가 있다(+7.5dB vs +1.9dB). **에너지 크기만으로는 구분 불가**이며,
**A안(자동 탐지 + 사람 검수)으로 진행 확정**됐다. 검수 절차는 docs/19.

**파일명 코드북**: `A{angle}_D{distance}_L{location}_P{pillar}_W{wall}_K{park}_{seq:03d}`
(pillar=P, park_position=K — P 충돌 회피). 읽는 법은 docs/19.

---

## 7. 자주 쓰는 명령

```bash
./scripts/dev.sh                     # 개발 서버 (백 :8100 + 프론트 :3100)
cd backend && uv run pytest -q       # 227 passed
cd frontend && npm run build         # 타입체크 + 빌드 (dev 서버 끄고)

railway up --detach                  # 백엔드 배포 (저장소 루트에서)
railway logs                         # 마이그레이션 확인
railway variables --kv               # env 확인 (공유 시 마스킹)
cd frontend && vercel deploy --prod  # 프론트 배포
```

**스킬 3종** — 같은 일을 손으로 재발명하지 말 것:
`audio-diagnose`(커팅 이상 → 실측 threshold 추천) ·
`finish-milestone`(DoD 체크 → §11 갱신 → 커밋) ·
`run-audio-platform`(앱 구동·브라우저 검증, `node driver.mjs smoke`)

---

## 8. 이 문서 유지 규칙

마일스톤이 끝나거나 **보류/대기 항목이 바뀌면 §3을 갱신**한다. §5는 새로 덴 것이
생길 때만 **추가**하고 지우지 않는다 — 다음 세션은 기억하지 못한다.
