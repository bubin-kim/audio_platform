# 20. NAS 자체 호스팅 (시놀로지 DS925+)

> 상태: **설치 안내 (v1.0, 2026-08-18)**
> 목적: 클라우드 요금 없이 NAS에서 플랫폼을 돌리고, 데이터를 전부 NAS에 둔다.

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
- 저장소 폴더 하나 (예: `/volume1/audio-platform`)

DS925+ 기본 RAM 4GB로 충분하다(백엔드+DB+프론트 합쳐 1GB 내외).

## 설치 절차

### 1. 파일 올리기

저장소 전체를 NAS의 공유 폴더에 복사한다. File Station이나 git 둘 다 가능:

```bash
# NAS에 SSH 접속 후 (제어판 > 터미널 및 SNMP > SSH 활성화)
cd /volume1/audio-platform
git clone https://github.com/bubin-kim/audio_platform.git .
```

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
2. 경로: `/volume1/audio-platform`, 소스: `docker-compose.nas.yml` 선택
3. 빌드가 5~10분 걸린다(처음 한 번만)

**방법 B — SSH**
```bash
cd /volume1/audio-platform
docker compose -f docker-compose.nas.yml up -d --build
docker compose -f docker-compose.nas.yml logs -f    # 진행 확인
```

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
/volume1/audio-platform/
├── data/          ← 오디오 원본·조각·CSV export (실제 용량 대부분)
│   ├── uploads/   ← 업로드한 원본
│   ├── segments/  ← 커팅된 조각
│   └── exports/   ← CSV
└── db/            ← PostgreSQL 데이터 (메타데이터·라벨)
```

**백업**: 시놀로지 Hyper Backup으로 이 두 폴더를 잡으면 된다. `db/`는 작지만
반드시 포함해야 한다 — 없으면 라벨·이력이 사라진다.

## 기존 Railway 데이터 옮기기

지금까지 Drive에 쌓인 것을 NAS로 가져오려면:

1. **오디오 파일**: Drive의 `audio_platform` 폴더를 통째로 내려받아
   `/volume1/audio-platform/data/`에 넣는다 (하위 구조 그대로).
2. **DB**: Railway에서 덤프 → NAS에서 복원
   ```bash
   # 로컬 PC에서
   railway run pg_dump --no-owner > dump.sql
   # NAS로 파일 옮긴 뒤
   docker compose -f docker-compose.nas.yml exec -T db \
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
