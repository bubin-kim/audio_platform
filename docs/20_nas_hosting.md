# 20. NAS 자체 호스팅 (시놀로지 DS925+)

> 상태: **설치 안내 (v1.0, 2026-08-18) → beep_sound_dataset 통합 (v1.1) →
> 01_BeepSound 3분할 (v1.2, 2026-08-27)**
> 목적: 클라우드 요금 없이 NAS에서 플랫폼을 돌리고, 데이터를 전부 NAS에 둔다.
>
> **2026-08-27, 두 차례 경로 변경이 있었다** (둘 다 교수님 지시):
> 1. `/volume1/audio-platform` → `/volume1/beep_sound_dataset`
>    (연구원 원본 폴더와 플랫폼 통합)
> 2. `/volume1/beep_sound_dataset` → **`/volume1/AURA/01_Projects/
>    01_BeepSound/{01_Raw,02_Dataset,03_Experiment}`** (원본·데이터셋·
>    실험환경 3분할)
>
> 아래 절차는 최종(3분할) 경로 기준으로 갱신했다. 상세 이전 기록은
> docs/21 §5 항목25(1차)·항목29(2차).

## 왜 NAS인가

| | 현재 (Railway + Drive) | NAS 자체 호스팅 |
|---|---|---|
| 월 비용 | Railway + Drive 100GB 요금 | **0원** |
| 저장 용량 | Drive 잔여 14GB (부족) | **16TB** |
| 오디오 처리 | Drive에서 내려받아 처리 | 로컬 디스크 — **더 빠름** |
| 외부 접속 | 어디서나 | QuickConnect 또는 내부망만 |
| 가동 조건 | 클라우드가 관리 | **NAS가 켜져 있어야 함** |

수집 규모 2,160클립 = 약 16.7GB(원본 8.5 + 조각 8.2)로 NAS 16TB에 여유가 많다.

## 준비물

- 시놀로지 DS925+ (DSM 7.2 이상)
- **Container Manager** 패키지 (패키지 센터에서 설치)
- 플랫폼 코드는 `/volume1/AURA/01_Projects/01_BeepSound/03_Experiment`
  (=`/volume1/@appdata/ContainerManager/all_shares/AURA/01_Projects/
  01_BeepSound/03_Experiment` — 같은 물리 위치를 가리키는 두 경로,
  Container Manager는 후자를 쓴다). §데이터가 어디에 쌓이나 참고.

DS925+ 기본 RAM 4GB로 충분하다(백엔드+DB+프론트 합쳐 1GB 내외).

## 설치 절차

### 1. 파일 올리기

저장소 전체를 NAS의 공유 폴더에 복사한다. File Station이나 git 둘 다 가능:

```bash
# NAS에 SSH 접속 후 (제어판 > 터미널 및 SNMP > SSH 활성화)
cd /volume1/AURA/01_Projects/01_BeepSound/03_Experiment
git clone https://github.com/bubin-kim/audio_platform.git .
```

**함정**: NAS에는 보통 `git`이 설치돼 있지 않다(`-sh: git: command not
found`). 코드 갱신은 맥 터미널에서 `scp -O <파일> <계정>@<NAS IP>:<경로>`로
개별 전송한다 — 반드시 NAS SSH 세션이 **아닌** 맥의 새 터미널에서 실행할
것(NAS 안의 구버전 scp는 `-O` 옵션을 모른다). 전송 후 `ls -la`로 mtime,
`grep`으로 실제 코드 내용이 바뀌었는지 직접 확인할 것 — "전송 완료"라는
말만으로는 실제 반영 여부를 알 수 없다(반복 실측됨, docs/21 §5 항목24).

### 2. 설정 파일 만들기

저장소 루트에 `.env` 파일을 만든다:

```bash
# 접속 암호 (연구실원에게 공유할 값)
ACCESS_TOKEN=원하는암호

# DB 비밀번호 (아무 값이나, 외부 노출 없음)
DB_PASSWORD=긴임의문자열

# 브라우저가 접근할 백엔드 주소
#  - 내부망만 쓸 때: http://NAS내부IP:8100/api
#  - QuickConnect 쓸 때: https://퀵커넥트주소:8100/api
PUBLIC_API_URL=http://192.168.0.x:8100/api

# 프론트 주소를 백엔드가 허용하도록 (CORS)
CORS_ORIGINS=http://192.168.0.x:3100

# 선택 — 없으면 해당 기능만 꺼진다
NTFY_TOPIC=
NOTION_API_KEY=
NOTION_DATABASE_ID=
```

> **주의**: `.env`는 git에 올라가지 않는다(비밀값 보관 규칙). NAS에서 직접 만든다.

### 3. 실행

**방법 A — Container Manager (GUI)**
1. Container Manager > 프로젝트 > 생성
2. 경로: `.../01_BeepSound/03_Experiment`, 소스: `compose.yaml`
   (=`docker-compose.nas.yml`) 선택
3. 빌드가 5~10분 걸린다(처음 한 번만)

**방법 B — SSH**
```bash
cd /volume1/AURA/01_Projects/01_BeepSound/03_Experiment
sudo docker compose up -d --build
sudo docker compose logs -f    # 진행 확인
```

일반 계정은 Docker 소켓 권한이 없어 `permission denied while trying to
connect to the Docker daemon socket`가 날 수 있다 — `sudo`를 붙인다.

**`02_Dataset/{uploads,segments,exports}` 폴더가 미리 있어야 한다** —
compose.yaml이 이 세 폴더를 형제 폴더(`02_Dataset`)에서 절대경로로
bind mount하는데(§데이터가 어디에 쌓이나), 폴더가 없으면
`Bind mount failed: '...' does not exist`로 기동이 실패한다. 특히
`exports`는 CSV export를 한 번도 실행 안 했으면 자동 생성 안 되어
있으니 미리 `mkdir -p exports`로 만들어 둘 것. 마운트 기준 경로는
`compose.yaml`의 `DATASET_DIR` 환경변수로 오버라이드할 수 있다
(`.env`에 `DATASET_DIR=/새경로`).

### 4. 접속 확인

- 프론트: `http://NAS내부IP:3100`
- 백엔드 상태: `http://NAS내부IP:8100/health` → `{"status":"ok"}`

### 5. 외부 접속 (선택)

연구실 밖에서도 쓰려면 **QuickConnect**가 가장 쉽다:
1. 제어판 > 외부 액세스 > QuickConnect 활성화
2. 역방향 프록시로 3100·8100 포트를 연결 (제어판 > 로그인 포털 > 고급)

포트포워딩보다 안전하고 공유기 설정이 필요 없다.

## 데이터가 어디에 쌓이나

```
/volume1/AURA/01_Projects/01_BeepSound/
├── 01_Raw/
│   └── mic1/, mic2/       ← 연구원이 올려두는 녹음 원본 (플랫폼 무관)
├── 02_Dataset/
│   ├── uploads/           ← 플랫폼에 업로드한 원본 (컨테이너 /data/uploads)
│   ├── segments/          ← 커팅된 조각 (컨테이너 /data/segments)
│   └── exports/           ← CSV export (컨테이너 /data/exports)
└── 03_Experiment/
    ├── backend/, frontend/  ← 플랫폼 코드
    ├── db/                  ← PostgreSQL 데이터 (메타데이터·라벨)
    └── compose.yaml, .env, CLAUDE.md, docs/, ...  ← 설정·문서
```

**컨테이너 볼륨 마운트는 절대경로 개별 마운트다** (`compose.yaml`은
`03_Experiment` 안에 있고 데이터는 형제 폴더 `02_Dataset`에 있어서):
```yaml
volumes:
  - ${DATASET_DIR:-/volume1/@appdata/.../01_BeepSound/02_Dataset}/uploads:/data/uploads
  - ${DATASET_DIR:-...}/segments:/data/segments
  - ${DATASET_DIR:-...}/exports:/data/exports
```
`db`는 `03_Experiment` 안에 있으므로 상대경로(`./db`) 그대로다.
`01_Raw`(mic1·mic2)는 플랫폼이 알 필요 없어 마운트하지 않는다.

**경로가 두 번 바뀐 이력**(전부 교수님 지시, 2026-08-27):
`audio-platform`(코드+데이터 한 폴더) → `beep_sound_dataset`(연구원
원본 폴더와 통합, `./data:/data` → 개별 마운트로 최초 분리) →
`01_BeepSound/{01_Raw,02_Dataset,03_Experiment}`(3분할, 절대경로
마운트로 전환). 상세는 docs/21 §5 항목25·29.

**백업**: 시놀로지 Hyper Backup으로 `02_Dataset`(uploads·segments·
exports)과 `03_Experiment/db`를 잡으면 된다. `db/`는 작지만 반드시
포함해야 한다 — 없으면 라벨·이력이 사라진다. `01_Raw`(원본 녹음)도
별도 백업 대상으로 챙길 것 — 이건 플랫폼이 관리하지 않는 연구원 직접
보관 폴더다.

## 기존 Railway 데이터 옮기기

지금까지 Drive에 쌓인 것을 NAS로 가져오려면:

1. **오디오 파일**: Drive의 `audio_platform` 폴더를 통째로 내려받아
   `02_Dataset/uploads/`, `02_Dataset/segments/`에 넣는다 (하위 구조
   그대로 — dataset id별 폴더).
2. **DB**: Railway에서 덤프 → NAS에서 복원
   ```bash
   # 로컬 PC에서
   railway run pg_dump --no-owner > dump.sql
   # NAS로 파일 옮긴 뒤 (03_Experiment에서)
   sudo docker compose exec -T db \
       psql -U audio audio_platform < dump.sql
   ```
3. 확인: 프로젝트·세그먼트 수가 이전과 같은지 화면에서 대조한다.

옮길 데이터가 적으면(파일럿 검증분뿐) **새로 시작하는 편이 간단하다** —
본수집 프로젝트만 다시 만들면 된다.

## 알아둘 것

- **NAS가 꺼지면 플랫폼도 멈춘다.** 연구실 정전·재부팅 시 컨테이너는
  `restart: unless-stopped`로 자동 복구되지만, NAS 자체가 켜져 있어야 한다.
- 업로드 상한이 기본 500MB로 잡혀 있다(`MAX_UPLOAD_MB`). 3분 녹음이 106MB라 여유롭다.
- 커팅은 백그라운드로 돈다. DS925+ 쿼드코어면 3분 원본 1개에 1~2분 예상
  (Railway보다 빠를 가능성이 높다 — 파일을 내려받지 않으므로).
- Railway·Vercel은 **당장 끄지 말고** NAS가 안정적으로 도는 것을 확인한 뒤 정리한다.
