"""탐지 성능 평가 — GT 대비 TP/FP/FN (순수 로직, P2).

**이 모듈은 탐지기와 동급이다.** 파라미터를 하나 바꿀 때마다 "좋아졌는지"를
숫자로 확인하지 않으면, 그럴듯해 보이는 변경이 실제로는 성능을 떨어뜨린다
(실제로 겪었다 — docs/17 §2b·§2e의 기각 사례들).

매칭 규칙(참고 구현과 동일):
  각 탐지 시점에 대해 tolerance 이내에서 **아직 매칭되지 않은** GT 중
  가장 가까운 것을 짝지운다. 한 GT는 한 번만 매칭된다 — 그래야 한 이벤트에
  여러 번 검출된 것이 TP로 중복 계산되지 않는다.

도메인 독립(P1): 경보음·심음 같은 값이 없다. GT 목록과 탐지 목록만 받는다.
"""

from dataclasses import dataclass, field

DEFAULT_TOLERANCE_SEC = 1.5


@dataclass
class MatchResult:
    """한 파일의 평가 결과."""

    tp: int
    fp: int
    fn: int
    tolerance_sec: float
    #: 매칭된 (GT 시각, 탐지 시각) 쌍 — 오차 분석용
    matches: list[tuple[float, float]] = field(default_factory=list)
    #: 매칭 안 된 탐지 시각 (헛것)
    false_positives: list[float] = field(default_factory=list)
    #: 매칭 안 된 GT 시각 (놓친 것)
    false_negatives: list[float] = field(default_factory=list)

    @property
    def recall(self) -> float:
        """놓치지 않은 비율 — 실제 이벤트 중 몇 %를 찾았나."""
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def precision(self) -> float:
        """헛것이 아닌 비율 — 찾은 것 중 몇 %가 진짜인가."""
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def detected_count(self) -> int:
        return self.tp + self.fp

    @property
    def gt_count(self) -> int:
        return self.tp + self.fn

    def summary(self) -> str:
        return (
            f"GT {self.gt_count} · 탐지 {self.detected_count} · "
            f"TP {self.tp} / FP {self.fp} / FN {self.fn} · "
            f"Recall {self.recall * 100:.1f}% · Precision {self.precision * 100:.1f}%"
        )


def evaluate(
    gt_times: list[float],
    detected_times: list[float],
    tolerance_sec: float = DEFAULT_TOLERANCE_SEC,
) -> MatchResult:
    """GT와 탐지 결과를 매칭해 TP/FP/FN을 센다.

    한 GT는 한 번만 매칭되고, 각 탐지는 tolerance 안의 **가장 가까운** 미매칭
    GT를 가져간다. 탐지를 시간순으로 훑으므로 결과는 결정적이다.
    """
    if tolerance_sec < 0:
        raise ValueError(f"tolerance_sec는 0 이상이어야 합니다. 받은 값: {tolerance_sec!r}")

    gt_sorted = sorted(float(t) for t in gt_times)
    det_sorted = sorted(float(t) for t in detected_times)

    matched_gt: set[int] = set()
    matches: list[tuple[float, float]] = []
    false_positives: list[float] = []

    for d in det_sorted:
        best_gi: int | None = None
        best_diff = tolerance_sec + 1
        for gi, g in enumerate(gt_sorted):
            if gi in matched_gt:
                continue
            diff = abs(d - g)
            if diff <= tolerance_sec and diff < best_diff:
                best_diff, best_gi = diff, gi
        if best_gi is None:
            false_positives.append(d)
        else:
            matched_gt.add(best_gi)
            matches.append((gt_sorted[best_gi], d))

    false_negatives = [g for gi, g in enumerate(gt_sorted) if gi not in matched_gt]
    return MatchResult(
        tp=len(matches),
        fp=len(false_positives),
        fn=len(false_negatives),
        tolerance_sec=tolerance_sec,
        matches=matches,
        false_positives=false_positives,
        false_negatives=false_negatives,
    )


def label_detections(
    gt_times: list[float],
    detected_times: list[float],
    tolerance_sec: float = DEFAULT_TOLERANCE_SEC,
) -> dict[float, str]:
    """탐지 시각 → "TP" | "FP" 라벨. 조각 메타데이터에 넣기 위한 형태.

    FN(놓친 GT)은 조각 자체가 없으므로 여기 담기지 않는다 — MatchResult의
    false_negatives를 따로 본다.
    """
    result = evaluate(gt_times, detected_times, tolerance_sec)
    labels = {det: "TP" for _gt, det in result.matches}
    labels.update({det: "FP" for det in result.false_positives})
    return labels


@dataclass
class ComparisonRow:
    """파라미터 조합 하나의 평가 결과 (비교표 한 줄)."""

    label: str
    params: dict
    per_file: dict[str, MatchResult]

    @property
    def total(self) -> MatchResult:
        """파일 전체를 합친 성능 — 조합끼리 비교할 때 이 값을 본다."""
        tp = sum(r.tp for r in self.per_file.values())
        fp = sum(r.fp for r in self.per_file.values())
        fn = sum(r.fn for r in self.per_file.values())
        tol = next(iter(self.per_file.values())).tolerance_sec if self.per_file else 0.0
        return MatchResult(tp=tp, fp=fp, fn=fn, tolerance_sec=tol)


def _width(text: str) -> int:
    """터미널 표시 폭 — 한글·전각 문자는 2칸을 차지한다."""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int, *, align: str = "left") -> str:
    """표시 폭 기준 정렬 (한글이 섞여도 컬럼이 안 밀린다)."""
    gap = max(0, width - _width(text))
    return text + " " * gap if align == "left" else " " * gap + text


def format_comparison(rows: list[ComparisonRow], *, file_order: list[str]) -> str:
    """비교표를 텍스트로. 파라미터를 바꿔가며 성능을 나란히 보기 위한 것.

    파일별로 (TP/FP/FN · Recall · Precision) 3칸, 마지막에 전체 합계.
    """
    if not rows:
        return "(비교할 결과가 없습니다)"

    # 파일명이 길면(한글 원본명 등) 표가 넘치므로 줄여 쓴다
    short = {n: (n if _width(n) <= 14 else "…" + n[-12:]) for n in file_order}

    label_w = max(10, max(_width(r.label) for r in rows) + 2)
    cols = [("TP/FP/FN", 11), ("R", 8), ("P", 8)]

    header = _pad("설정", label_w)
    for name in file_order:
        block = sum(w for _, w in cols)
        header += _pad(short[name], block, align="right")
    header += _pad("전체 R", 9, align="right")
    header += _pad("전체 P", 9, align="right")
    header += _pad("F1", 7, align="right")

    sub = _pad("", label_w)
    for _ in file_order:
        for title, w in cols:
            sub += _pad(title, w, align="right")
    sub += _pad("", 25)

    lines = [header, sub, "-" * _width(header)]

    for row in rows:
        line = _pad(row.label, label_w)
        for name in file_order:
            r = row.per_file.get(name)
            if r is None:
                for _, w in cols:
                    line += _pad("—", w, align="right")
                continue
            line += _pad(f"{r.tp}/{r.fp}/{r.fn}", cols[0][1], align="right")
            line += _pad(f"{r.recall * 100:.1f}%", cols[1][1], align="right")
            line += _pad(f"{r.precision * 100:.1f}%", cols[2][1], align="right")
        t = row.total
        line += _pad(f"{t.recall * 100:.1f}%", 9, align="right")
        line += _pad(f"{t.precision * 100:.1f}%", 9, align="right")
        line += _pad(f"{t.f1 * 100:.1f}", 7, align="right")
        lines.append(line)
    return "\n".join(lines)
