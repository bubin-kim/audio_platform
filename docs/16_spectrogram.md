# 16. 스펙트로그램 시각화 + 원본 섹션 (V2-8)

> 상태: **설계안 (v1.0, 2026-08-04)** — 사용자 결정 반영: 원본 표시 위치=데이터셋
> 상세에 원본 섹션 신설, 주파수 축=로그(멜) 스케일.
> 배경: 환경음에 묻힌 이벤트(예: 260804_005.WAV의 경적)가 웨이브폼에는 안 보이지만
> 스펙트로그램의 대역 에너지로는 보인다 — 수집 현장에서 녹음 품질을 눈으로 판단하는 도구.

## 1. 목표와 범위

- **A. 원본 스펙트로그램**: 데이터셋 상세에 **"원본 파일" 섹션 신설** — 파일명·업로더
  (V2-7 잔여 해소)·길이 목록 + 행마다 통 음원 스펙트로그램. 업로드 직후에는 기존
  "데이터셋으로 이동" 링크로 도달한다.
- **B. 세그먼트 스펙트로그램**: 세그먼트 테이블의 기존 미니 파형 **옆에** 같은 크기의
  미니 스펙트로그램.
- 주파수 축은 **멜(로그) 스케일** — 저음(심음)~고음 도메인 전부에서 유효, 도메인
  전용 설정 없음(P1). 표시 상한은 파일의 나이퀴스트(sr/2)를 그대로 따른다.

**비목표**: 재생 위치 커서 연동, 확대/구간 선택, 스펙트로그램 기반 커팅(별도 제안),
서버측 PNG 렌더(새 의존성 금지 — matplotlib 불필요).

## 2. 아키텍처 (기존 waveform 패턴 그대로)

```
audio/spectrogram.py (순수 계산, librosa)  ← P2: web/DB import 없음
  → services/… (storage.local_path로 파일 접근)
  → api: GET /segments/{id}/spectrogram · GET /source-files/{id}/spectrogram
  → frontend: <Spectrogram> 캔버스 렌더 (JSON 수신 → 컬러맵)
```

- 계산: `librosa.feature.melspectrogram` → dB 변환 → **0~100 uint8 양자화** →
  base64 문자열로 응답 (3분 원본 ≈ 800열×96멜 ≈ 77KB — JSON 2D 배열 대비 1/6).
- 열 수는 길이에 비례하되 상한: 원본 max 800열, 세그먼트 max 240열.
- 파일 불변 → `Cache-Control: private, max-age=3600` (waveform과 동일).
- 인증: api.ts `request()` 경유(XHR + Bearer 헤더)라 쿼리 토큰 불필요.

## 3. API (docs/06 갱신 대상)

| 엔드포인트 | 응답 |
|---|---|
| `GET /api/segments/{id}/spectrogram` | `SpectrogramRead` |
| `GET /api/source-files/{id}/spectrogram` | `SpectrogramRead` |
| `GET /api/datasets/{id}/sources` | `Page[SourceRead]` — **원본 목록 신설** (uploaded_by 포함) |

```json
SpectrogramRead {
  "duration_sec": 184.1, "sample_rate": 48000,
  "n_mels": 96, "cols": 800, "fmax": 24000,
  "db_floor": -80.0, "db_ceil": 0.0,
  "data": "<base64 uint8, n_mels×cols, 행=저음→고음>"
}
```

## 4. 프론트

| 위치 | 변경 |
|---|---|
| `components/datasets/Spectrogram.tsx` 신설 | base64 디코드 → `<canvas>` 렌더. 컬러맵·접근성은 구현 시 dataviz 스킬 기준 적용 |
| 데이터셋 상세 | **원본 파일 섹션** 신설: 파일명·업로더·길이·포맷 + 행 펼치면 스펙트로그램(지연 로드 — 펼칠 때 fetch) |
| `SegmentTable.tsx` | 파형 열 옆 "스펙트럼" 열 추가 (미니, 파형과 동일 지연 로드 방식) |

## 5. 마일스톤

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| **S-M1** | audio/spectrogram.py + 엔드포인트 3종 + 테스트 | 전체 pytest green (양자화·열 상한·404 케이스 포함) |
| **S-M2** | Spectrogram 컴포넌트 + 원본 섹션 + 세그먼트 열 | `npm run build` + 격리 브라우저 검증 (260804_005 업로드 → 경적 대역이 눈에 보이는지 스크린샷) |
| **S-M3** | 실배포 + docs/06 갱신 | 실서버에서 원본·세그먼트 스펙트로그램 표시 확인, 임시 데이터 정리 |

## 6. 리스크 / 한계

| 항목 | 내용 |
|---|---|
| 원본 계산 시간 | 3분 파일 멜 계산 ~1-2초(온디맨드) — 첫 조회만 느림, 이후 브라우저 캐시. 병목이면 후속으로 서버 캐시 검토 |
| drive_primary | storage.local_path가 Drive에서 내려받음(로컬 캐시 재사용) — 첫 조회 지연 가능 |
| 긴 파일 | 800열 상한이라 3분 넘는 파일은 시간 해상도가 거칠어짐 (0.2~0.5초/열) — 관찰용으로 충분 |
| 동시 요청 폭주 | **실사고(2026-08-04)**: 세그먼트 테이블이 파형+스펙트럼을 마운트 즉시 fetch하도록 짜여 있어, 37세그먼트 데이터셋 진입 시 74개 요청이 동시에 나가 DB 커넥션 풀(5+10)이 고갈 → TimeoutError로 다수 실패(기존 파형 기능까지 회귀). `useLazyVisible`(IntersectionObserver)로 뷰포트 진입 시에만 로드하도록 수정 — 요청 수가 뷰포트 분량(~12개)으로 줄어듦. **교훈**: 세그먼트마다 1개씩 붙는 시각화는 설계 단계부터 지연 로드를 기본으로 삼을 것 (원본 목록은 처음부터 수동 토글로 설계해 이 문제가 없었음). |
