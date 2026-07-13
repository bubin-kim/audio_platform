# 08 — 커팅 파라미터 튜닝 가이드 (silence_based)

> **목적**: silence_based 커팅이 기대와 다르게 동작할 때(조각이 0개/1개로 나올 때)
> **코드가 아니라 설정을** 진단·조정하는 방법을 남긴다. 커팅 파라미터는 전부
> Project 설정(P1)이므로, 이 가이드의 결론은 항상 "설정 변경"이지 코드 수정이 아니다.
> 실전 사례: 2026-07-11 심음(heartbeat) 30초 파일 튜닝 과정.

---

## 1. 파라미터가 하는 일 (판정 순서대로)

silence_based는 **20ms 창을 10ms 간격**으로 훑으며 RMS를 재고, 아래 순서로 판정한다.

| 순서 | 파라미터 | 기본값 | 역할 | 잘못되면 |
|---|---|---|---|---|
| ① | `silence_threshold_db` | -40 | 이 값(dBFS) **미만이면 무음** | 너무 낮으면 무음 감지 0회 → **1조각(전체)** |
| ② | `min_silence_sec` | 0.3 | 무음이 이보다 길어야 **구분점** | 너무 길면 이벤트들이 한 조각으로 붙음 |
| ③ | `min_segment_sec` | 0.2 | 코어(패딩 제외)가 이보다 짧으면 **버림** | 너무 길면 짧은 이벤트 전멸 → **0조각** |
| ④ | `max_segment_sec` | 없음 | 넘으면 강제 분할 | (안전장치, 보통 불필요) |
| ⑤ | `padding_sec` | 0.1 | 조각 앞뒤 여유 (min_silence/2로 클램프) | — |

**핵심 함정 두 가지** (실제로 둘 다 밟았다):
- ①의 threshold는 **절대 dBFS**다. "무음"이어도 녹음에는 배경 노이즈 바닥이 있다
  (마이크·프리앰프·환경). **threshold가 노이즈 바닥보다 낮으면 무음이 영원히 감지되지 않는다.**
- ③의 길이 기준은 **패딩을 제외한 코어 길이**다. Segment의 최종 duration이 아니라
  "실제 소리 구간"이 기준이므로, 눈에 보이는 조각 길이보다 엄격하다.

---

## 2. 증상별 진단

### 증상 A: 조각이 1개(파일 전체)로 나온다
→ 무음을 한 번도 못 찾은 것. **threshold가 배경 노이즈 바닥보다 낮다.**

**진단**: 파일의 프레임 RMS 분포를 재서 배경 레벨을 확인한다 (전략과 동일한 20ms/10ms):

```python
# backend에서: uv run python  (audio/는 앱 없이 독립 실행 가능 — P2)
import numpy as np, soundfile as sf
y, sr = sf.read("../data/uploads/<id>/<파일>.wav", dtype="float32", always_2d=False)
if y.ndim > 1: y = y.mean(axis=1)
frame, hop = int(0.02*sr), int(0.01*sr)
rms = np.array([np.sqrt(np.mean(np.square(y[i:i+frame], dtype=np.float64)))
                for i in range(0, len(y)-frame+1, hop)])
db = 20*np.log10(np.maximum(rms, 1e-12))
print("배경(하위 50%) 평균:", db[db <= np.median(db)].mean().round(1), "dBFS")
print("이벤트(상위 10%) 평균:", db[db >= np.percentile(db, 90)].mean().round(1), "dBFS")
```

**처방**: threshold를 **배경보다 5~10dB 위, 이벤트보다 충분히 아래**로.
예: 배경 -42 / 이벤트 -16 → **-35** (배경 +7dB, 이벤트 -19dB 여유).

### 증상 B: 조각이 0개로 나온다 (Job은 done, error 없음)
→ 무음 감지는 됐지만 **모든 소리 구간이 `min_segment_sec`보다 짧아 전부 탈락**한 것.

**진단**: `min_segment_sec: 0`으로 전략을 직접 돌려 원시 코어 길이를 본다:

```python
from pathlib import Path
from app.audio.cutting import get_strategy
segs = list(get_strategy("silence_based").cut(
    Path("../data/uploads/<id>/<파일>.wav"),
    {"silence_threshold_db": -35, "min_silence_sec": 0.15, "min_segment_sec": 0.0},
))
print(len(segs), "개, 길이", [round(s.duration_sec, 2) for s in segs[:10]])
```

**처방**: `min_segment_sec`를 **가장 짧은 유효 이벤트 코어보다 작게** 설정.
스파이크 제거 기능은 유지되도록 0으로 만들지는 말 것 (예: 0.05~0.1).

### 증상 C: 이벤트 여러 개가 한 조각으로 붙는다
→ 이벤트 사이 간격이 `min_silence_sec`보다 짧다. 값을 줄인다 (단, 너무 줄이면
하나의 이벤트 내부 미세한 조용한 순간에서도 쪼개진다 — 증상 D).

### 증상 D: 조각이 지나치게 잘게 쪼개진다
→ `min_silence_sec`를 늘리거나(이벤트 내부 숨 고르기를 무시), threshold를 낮춘다.

---

## 3. 실전 사례: 심음 30초 파일 (2026-07-11)

| 단계 | 설정 | 결과 | 원인 |
|---|---|---|---|
| 1차 | th=-45, min_sil=0.15, min_seg=0.3 | **1조각(30s)** | 배경 노이즈 -42.1 dBFS > threshold -45 → 무음 감지 0/2999 프레임 |
| 2차 | th=**-35**, min_sil=0.15, min_seg=0.3 | **0조각** | 비트 코어가 0.15~0.29s < min_seg 0.3 → 33개 전부 탈락 |
| 3차 | th=-35, min_sil=0.15, min_seg=**0.1** | ✅ **33조각** (0.30~0.44s) | — |

측정값: 배경(비트 사이) 평균 **-42.1 dBFS**, 이벤트(비트) 평균 **-15.9 dBFS**.

### 실전 사례 2: 지하주차장 비프음 60초 (2026-07-13, 파일럿 프록시 진단)

- 파일: parking_beep_1min.wav (44.1kHz, 비프 2초 + 간격 4초 × 10회)
- **배경소음 바닥이 -34dBFS로 높음** (지하주차장 잔향·환기 소음) → 기본 threshold -40은
  바닥보다 낮아서 무음 판정 0% → 60초 통짜 1조각 (증상 A).
- audio-diagnose 추천값 **-21dBFS**(바닥 p10 -34.2 ↔ 신호 p90 -7.4의 중간) 적용 시
  10개 비프가 각각 ~2.2초 조각으로 정확히 분리됨.
- **교훈**: 지하주차장류 실환경은 threshold를 반드시 실측으로 정한다. 마이크·게인이
  바뀌면 바닥도 바뀌므로 **수집 당일 첫 녹음으로 재진단**하고 시작할 것.

## 4. 도메인별 출발점 (권장 초기값)

실측 후 조정하는 것이 원칙이지만, 출발점으로:

| 도메인 특성 | threshold | min_silence | min_segment | 근거 |
|---|---|---|---|---|
| **짧은 반복 이벤트** (심음, 비프음) | -35 | 0.15 | **0.05~0.1** | 이벤트 코어가 0.3s 미만으로 짧음 |
| **긴 단발 이벤트** (경적, 통과음) | -40 | 0.3~0.5 | 0.3 | 기본값 부근 |
| **조용한 환경 녹음** (스튜디오) | -45~-50 | 0.3 | 0.2 | 노이즈 바닥이 낮음 |
| **시끄러운 환경** (도로변, 공장) | -25~-30 | 0.2 | 0.2 | 노이즈 바닥이 높음 |

> 어떤 값이든 **먼저 §2-A의 분포 측정**으로 배경/이벤트 레벨을 확인하는 것이 가장 빠르다.

## 5. 실험 워크플로우

1. **1회성 실험**: `POST /api/datasets/{id}/process`의 `params_override`로 값만 바꿔 시도.
   (Job.params에 기록되므로 어떤 값으로 돌렸는지 재현 가능 — 05 §3.5)
2. **확정되면**: `PATCH /api/projects/{id}`의 `cutting_params`로 영구 반영.
3. 재처리 전 기존 세그먼트 정리 필요 시: 같은 원본을 다시 process하면 세그먼트가
   누적되므로, 기존 조각을 지우고 돌리거나 새 Dataset에서 실험한다.
4. 같은 파일을 두 번 업로드했다면 SourceFile row가 중복된다 —
   `source_file_ids`로 하나만 지정해 중복 커팅을 피한다.
