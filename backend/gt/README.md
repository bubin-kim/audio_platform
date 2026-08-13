# Ground Truth (정답 타임스탬프)

사람이 직접 청취해 만든 이벤트 발생 시각 목록. 탐지 성능을 재는 기준이다.

## 형식

파일 하나당 JSON 하나. 파일명은 자유(원본과 맞추는 걸 권장).

```json
{
  "source_filename": "파일럿_004.WAV",
  "event_times_sec": [4, 9, 15, ...],
  "note": "사람이 청취 확인. 6초 주기로 반복되는 경보음",
  "verified_by": "사용자",
  "verified_at": "2026-08-13"
}
```

- `event_times_sec` (필수): 이벤트 시각(초). 정수·소수 모두 가능.
- 나머지는 선택 — 출처를 남겨두면 나중에 이 GT를 믿어도 되는지 판단할 수 있다.

## 쓰는 법

```bash
cd backend
uv run python scripts/evaluate_detection.py \
    --audio /경로/파일럿_004.WAV --gt gt/pilot_004.json
```

여러 파일·파라미터 조합 비교는 `--help` 참조.

## 새 파일을 추가하려면

JSON 하나만 이 폴더에 더하면 된다. 코드 수정 불필요.
