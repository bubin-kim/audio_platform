"""오디오 파일 무음 프로파일 진단 — silence_based 파라미터 튜닝용 (docs/08 참조).

backend/ 디렉토리에서 실행한다 (app 패키지 import를 위해):
    cd backend && uv run python ../.claude/skills/audio-diagnose/diagnose.py <wav경로> \
        [--threshold-db -40] [--min-silence-sec 0.3] [--min-segment-sec 0.2]

출력:
  1) 파일 기본 정보 (길이·SR·peak/RMS dBFS)
  2) 20ms 창 RMS 분포 백분위 — "무음 바닥"과 "신호 수준"이 몇 dB인지
  3) 주어진 파라미터로 실제 SilenceBasedStrategy를 돌린 결과 (조각 수·경계)
  4) 추천 threshold (바닥 p10과 신호 p90의 중간값)
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# backend/ 에서 실행된다는 전제 (아래 SKILL.md 참조).
sys.path.insert(0, str(Path.cwd()))
try:
    from app.audio.cutting import get_strategy
except ImportError:
    sys.exit("ERROR: backend/ 디렉토리에서 실행하세요: cd backend && uv run python ../.claude/...")


def main() -> None:
    ap = argparse.ArgumentParser(description="silence_based 커팅 진단")
    ap.add_argument("path", help="분석할 오디오 파일 경로")
    ap.add_argument("--threshold-db", type=float, default=-40.0)
    ap.add_argument("--min-silence-sec", type=float, default=0.3)
    ap.add_argument("--min-segment-sec", type=float, default=0.2)
    args = ap.parse_args()

    data, sr = sf.read(args.path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    duration = len(data) / sr

    def to_db(x: np.ndarray | float) -> np.ndarray | float:
        return 20 * np.log10(np.maximum(x, 1e-10))

    frame = max(1, int(0.02 * sr))
    hop = max(1, int(0.01 * sr))
    n = 1 + max(0, (len(data) - frame) // hop)
    rms = np.sqrt(
        np.array([np.mean(np.square(data[i * hop : i * hop + frame])) for i in range(n)])
    )
    rms_db = to_db(rms)

    print(f"== 파일: {args.path}")
    print(f"   길이 {duration:.2f}초 · {sr}Hz · peak {to_db(np.max(np.abs(data))):.1f} dBFS"
          f" · 전체 RMS {to_db(float(np.sqrt(np.mean(np.square(data))))):.1f} dBFS")

    print("\n== 20ms 창 RMS 분포 (dBFS) — p10 근처가 '무음 바닥', p90 근처가 '신호 수준'")
    for p in (5, 10, 25, 50, 75, 90, 95):
        print(f"   p{p:<3} {float(np.percentile(rms_db, p)):8.1f}")

    silent_ratio = float(np.mean(rms_db < args.threshold_db))
    print(f"\n== threshold {args.threshold_db:.0f} dBFS 기준: 전체의 {silent_ratio*100:.0f}%가 무음 판정")
    if silent_ratio < 0.02:
        print("   → 무음이 거의 안 잡힘: threshold가 너무 낮다(엄격). 올려볼 것 (예: -35, -30).")
    if silent_ratio > 0.9:
        print("   → 거의 전부 무음 판정: threshold가 너무 높다. 내려볼 것 (예: -50).")

    params = {
        "silence_threshold_db": args.threshold_db,
        "min_silence_sec": args.min_silence_sec,
        "min_segment_sec": args.min_segment_sec,
    }
    segs = list(get_strategy("silence_based").cut(Path(args.path), params))
    print(f"\n== 이 파라미터로 실제 커팅 시뮬레이션: {len(segs)}개 조각")
    for s in segs[:15]:
        print(f"   #{s.index}: {s.start_sec:7.2f}s ~ {s.end_sec:7.2f}s ({s.duration_sec:.2f}초)")
    if len(segs) > 15:
        print(f"   ... 외 {len(segs) - 15}개")

    floor, signal = float(np.percentile(rms_db, 10)), float(np.percentile(rms_db, 90))
    suggested = (floor + signal) / 2
    print(f"\n== 추천 threshold: {suggested:.0f} dBFS (바닥 p10 {floor:.1f} ↔ 신호 p90 {signal:.1f}의 중간)")
    if signal - floor < 10:
        print("   ⚠ 바닥과 신호 차이가 10dB 미만 — 무음 기반 커팅이 애초에 어려운 녹음일 수 있다.")
        print("     docs/08의 '증상별 진단' 참조. fixed_interval 또는 max_segment_sec 병용 검토.")


if __name__ == "__main__":
    main()
