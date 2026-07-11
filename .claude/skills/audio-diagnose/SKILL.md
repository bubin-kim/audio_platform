---
name: audio-diagnose
description: 커팅 결과가 이상할 때(조각이 1개만 나옴, 무음을 못 찾음, 조각이 너무 많음/적음) 원본 오디오의 RMS/dBFS 프로파일을 분석하고 silence_based 파라미터를 추천·재처리. "커팅이 N조각밖에 안 나와", "무음 구간을 못 찾아", "threshold 튜닝" 같은 요청에 사용.
---

silence_based 커팅이 기대와 다르게 나올 때의 진단 루틴. 추측으로 파라미터를
바꾸지 말고, **원본 파일의 실제 dB 분포를 먼저 측정**한다. 지식 베이스는
docs/08_cutting_tuning.md(증상별 진단 표·심음 실전 사례) — 진단 전에 읽는다.

## 입력

- 문제가 된 **원본 파일 경로** — 업로드 원본은 `data/uploads/{source_id}/` 아래.
  모르면 DB에서 찾는다: dataset 상세 API 또는
  `sqlite3 audio_platform.db "SELECT id, storage_path FROM source_files WHERE dataset_id=<N>"`
- 현재 프로젝트의 cutting_params (프로젝트 상세 API나 UI에서 확인)

## 단계

1. **진단 스크립트 실행** (반드시 backend/에서):
   ```bash
   cd backend && uv run python ../.claude/skills/audio-diagnose/diagnose.py \
       <원본파일경로> --threshold-db <현재값> --min-silence-sec <현재값>
   ```
   출력에서 볼 것: ① 무음 바닥(p10)과 신호(p90)의 dB 값, ② 현재 threshold로
   무음 판정된 비율, ③ 실제 커팅 시뮬레이션 조각 수, ④ 추천 threshold.
2. **해석** (docs/08 증상 표와 대조):
   - 조각 1개뿐 + 무음 판정 ~0% → threshold가 배경소음보다 낮다. 추천값으로 올린다.
   - 조각 0개 → threshold가 신호보다 높다. 내린다.
   - 조각이 너무 잘게 나뉨 → `min_silence_sec`를 키우거나 `min_segment_sec`로 거른다.
   - 바닥↔신호 차이 < 10dB → 무음 커팅 자체가 부적합. fixed_interval 또는
     `max_segment_sec` 병용을 사용자에게 제안한다.
3. **파라미터 변경 제안**: 추천값과 근거(측정 수치)를 사용자에게 보여주고 승인받는다.
   승인 후 프로젝트 설정 변경은 API로:
   ```bash
   curl -X PATCH http://localhost:8000/api/projects/<id> \
     -H "Content-Type: application/json" \
     -d '{"cutting_params": {"silence_threshold_db": -35, "min_silence_sec": 0.3}}'
   ```
   (UI로 하려면 프로젝트 상세 → 설정 수정. 서버는 `./scripts/dev.sh`로.)
4. **재처리**: 기존 잘못된 세그먼트를 지울지 사용자에게 확인 후, 커팅 재실행
   (`POST /api/datasets/<id>/process`). 결과 조각 수가 시뮬레이션과 일치하는지 확인.
5. **기록**: 새로 알게 된 도메인별 특성(예: "심음은 -45/-0.15가 잘 맞음")은
   docs/08에 사례로 추가한다.

## 주의

- diagnose.py의 시뮬레이션은 실제 `SilenceBasedStrategy` 코드를 그대로 돌린 결과라
  재처리 결과와 반드시 일치한다. 다르면 파라미터가 프로젝트에 저장 안 된 것.
- 파일이 mp3/m4a면 스크립트가 soundfile로 읽는다(ffmpeg 필요한 포맷은 wav로 변환 후).
- 세그먼트 삭제는 되돌릴 수 없으므로 **반드시 사용자 확인 후** 진행.
