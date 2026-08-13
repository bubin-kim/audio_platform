"""탐지 성능 평가 CLI — GT 대비 TP/FP/FN을 재고, 파라미터 조합을 비교한다.

**파라미터를 바꿀 때마다 이걸 돌려서 수치로 확인한다.** 그럴듯해 보이는 변경이
실제로는 성능을 떨어뜨리는 일이 반복해서 있었다(docs/17 §2b·§2e 기각 사례).

사용법:

  # 한 파일 평가 (기본 파라미터)
  uv run python scripts/evaluate_detection.py \\
      --audio ~/audio/파일럿_004.WAV --gt gt/pilot_004.json

  # 여러 파일 한 번에
  uv run python scripts/evaluate_detection.py \\
      --audio a.WAV --gt gt/pilot_004.json \\
      --audio b.WAV --gt gt/pilot_005.json

  # 파라미터 하나를 여러 값으로 훑기 (비교표)
  uv run python scripts/evaluate_detection.py ... --sweep height_db=3,4,5,6,7

  # 옵션 켜고 끄기 비교
  uv run python scripts/evaluate_detection.py ... --sweep periodic_rescue=false,true

  # 놓친 것·헛것 목록까지 보기
  uv run python scripts/evaluate_detection.py ... --detail
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio.cutting.event_detection import (  # noqa: E402
    DEFAULTS,
    EventDetectionStrategy,
)
from app.audio.evaluation import (  # noqa: E402
    DEFAULT_TOLERANCE_SEC,
    ComparisonRow,
    evaluate,
    format_comparison,
)


def _parse_value(raw: str):
    """스윕 값 문자열 → 파이썬 값 (bool·숫자·문자열)."""
    low = raw.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("none", "null"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _load_gt(path: Path) -> tuple[list[float], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    times = data.get("event_times_sec")
    if not isinstance(times, list) or not times:
        raise ValueError(f"{path}: event_times_sec(목록)가 필요합니다.")
    label = data.get("source_filename") or path.stem
    return [float(t) for t in times], str(label)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="이벤트 탐지 성능 평가 (GT 대비 TP/FP/FN)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--audio", action="append", required=True, help="원본 오디오 경로")
    ap.add_argument("--gt", action="append", required=True, help="GT JSON 경로")
    ap.add_argument(
        "--tolerance", type=float, default=DEFAULT_TOLERANCE_SEC,
        help=f"매칭 허용 오차(초). 기본 {DEFAULT_TOLERANCE_SEC}",
    )
    ap.add_argument(
        "--param", action="append", default=[],
        help="고정 파라미터 (key=value). 예: --param height_db=5",
    )
    ap.add_argument(
        "--sweep", default=None,
        help="훑을 파라미터 (key=v1,v2,...). 예: --sweep height_db=3,4,5",
    )
    ap.add_argument("--detail", action="store_true", help="놓친 것·헛것 목록도 출력")
    args = ap.parse_args()

    if len(args.audio) != len(args.gt):
        ap.error(f"--audio({len(args.audio)}개)와 --gt({len(args.gt)}개) 개수가 달라야 합니다")

    base_params: dict = {}
    for item in args.param:
        if "=" not in item:
            ap.error(f"--param 형식은 key=value 입니다: {item!r}")
        k, v = item.split("=", 1)
        base_params[k.strip()] = _parse_value(v)

    # 평가 대상 파일 로드
    targets = []
    for audio, gt in zip(args.audio, args.gt):
        audio_path, gt_path = Path(audio), Path(gt)
        if not audio_path.exists():
            print(f"오디오 없음: {audio_path}", file=sys.stderr)
            return 1
        if not gt_path.exists():
            print(f"GT 없음: {gt_path}", file=sys.stderr)
            return 1
        times, label = _load_gt(gt_path)
        targets.append((label, audio_path, times))

    # 파라미터 조합 목록
    if args.sweep:
        if "=" not in args.sweep:
            ap.error("--sweep 형식은 key=v1,v2,... 입니다")
        key, raw_values = args.sweep.split("=", 1)
        key = key.strip()
        if key not in DEFAULTS:
            print(f"경고: '{key}'는 알려진 파라미터가 아닙니다 (전략이 무시할 수 있음)",
                  file=sys.stderr)
        combos = [
            (f"{key}={v}", {**base_params, key: _parse_value(v)})
            for v in raw_values.split(",")
        ]
    else:
        combos = [("기본" if not base_params else "지정 파라미터", base_params)]

    strategy = EventDetectionStrategy()
    rows: list[ComparisonRow] = []
    for label, params in combos:
        per_file = {}
        for name, audio_path, gt_times in targets:
            events = strategy.detect_events(audio_path, params)
            detected = [e.center_sec for e in events]
            per_file[name] = evaluate(gt_times, detected, args.tolerance)
        rows.append(ComparisonRow(label=label, params=params, per_file=per_file))

    file_order = [name for name, _, _ in targets]
    print(f"\n허용 오차 {args.tolerance}초 · 파일 {len(targets)}개")
    print(format_comparison(rows, file_order=file_order))

    if args.detail:
        for row in rows:
            print(f"\n[{row.label}]")
            for name in file_order:
                r = row.per_file[name]
                print(f"  {name}: {r.summary()}")
                if r.false_negatives:
                    print(f"    놓침(FN) {len(r.false_negatives)}개: "
                          f"{[round(t, 1) for t in r.false_negatives]}")
                if r.false_positives:
                    print(f"    헛것(FP) {len(r.false_positives)}개: "
                          f"{[round(t, 1) for t in r.false_positives]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
