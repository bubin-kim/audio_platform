"""탐지 성능 평가 모듈 테스트 (app/audio/evaluation.py).

이 모듈은 탐지기와 동급이다 — 여기가 틀리면 모든 파라미터 판단이 틀어진다.
"""

import pytest

from app.audio.evaluation import (
    ComparisonRow,
    evaluate,
    format_comparison,
    label_detections,
)


def test_perfect_match() -> None:
    r = evaluate([10.0, 20.0, 30.0], [10.0, 20.0, 30.0])
    assert (r.tp, r.fp, r.fn) == (3, 0, 0)
    assert r.recall == 1.0 and r.precision == 1.0 and r.f1 == 1.0


def test_within_tolerance_counts_as_hit() -> None:
    """허용 오차 안이면 같은 이벤트로 본다."""
    r = evaluate([10.0], [11.4], tolerance_sec=1.5)
    assert (r.tp, r.fp, r.fn) == (1, 0, 0)


def test_outside_tolerance_is_fp_and_fn() -> None:
    """오차를 벗어나면 헛것 1 + 놓침 1 (둘 다 계산된다)."""
    r = evaluate([10.0], [11.6], tolerance_sec=1.5)
    assert (r.tp, r.fp, r.fn) == (0, 1, 1)
    assert r.false_positives == [11.6]
    assert r.false_negatives == [10.0]


def test_one_gt_matches_only_once() -> None:
    """한 이벤트에 두 번 검출되면 하나만 TP — 나머지는 FP다.

    이 규칙이 없으면 같은 자리를 여러 번 찍는 것만으로 성능이 부풀려진다.
    """
    r = evaluate([10.0], [9.8, 10.2])
    assert (r.tp, r.fp, r.fn) == (1, 1, 0)


def test_closest_gt_wins() -> None:
    """탐지는 tolerance 안에서 가장 가까운 GT와 짝지어진다."""
    r = evaluate([10.0, 11.0], [10.9])
    assert r.matches == [(11.0, 10.9)]


def test_empty_detection() -> None:
    r = evaluate([10.0, 20.0], [])
    assert (r.tp, r.fp, r.fn) == (0, 0, 2)
    assert r.recall == 0.0
    assert r.precision == 0.0  # 분모 0 — 0으로 나누지 않는다


def test_empty_gt() -> None:
    r = evaluate([], [10.0])
    assert (r.tp, r.fp, r.fn) == (0, 1, 0)
    assert r.recall == 0.0


def test_unsorted_input_is_handled() -> None:
    """입력 순서에 의존하지 않는다."""
    a = evaluate([30.0, 10.0, 20.0], [20.1, 9.9, 29.8])
    b = evaluate([10.0, 20.0, 30.0], [9.9, 20.1, 29.8])
    assert (a.tp, a.fp, a.fn) == (b.tp, b.fp, b.fn) == (3, 0, 0)


def test_negative_tolerance_rejected() -> None:
    with pytest.raises(ValueError, match="tolerance_sec"):
        evaluate([1.0], [1.0], tolerance_sec=-1)


def test_reproduces_pilot_004_numbers() -> None:
    """검증된 파일럿 결과(TP 24/FP 7/FN 7)를 매칭 규칙만으로 재현한다.

    실제 탐지 시각을 넣어, 평가 로직이 그 표를 만들어내는지 고정한다.
    """
    gt = [4, 9, 15, 21, 27, 33, 39, 45, 51, 57, 63, 69, 75, 80, 87, 93, 99,
          105, 111, 117, 123, 129, 135, 141, 147, 154, 159, 165, 171, 177, 183]
    # 플랫폼 탐지기가 실제로 낸 시각 (기본 파라미터, 2026-08-13 실측)
    detected = [
        3.85, 10.03, 15.49, 21.76, 27.68, 33.69, 40.7, 45.77, 52.08, 57.98,
        63.9, 68.08, 73.4, 79.53, 84.17, 90.26, 95.43, 100.7, 105.56, 111.64,
        116.17, 128.24, 135.4, 141.11, 148.93, 154.27, 159.06, 165.93, 171.85,
        178.0, 183.95,
        ]
    r = evaluate(gt, detected, tolerance_sec=1.5)
    assert (r.tp, r.fp, r.fn) == (24, 7, 7), r.summary()
    assert abs(r.recall - 24 / 31) < 1e-9
    assert abs(r.precision - 24 / 31) < 1e-9


def test_label_detections_marks_tp_and_fp() -> None:
    labels = label_detections([10.0, 20.0], [10.1, 15.0])
    assert labels[10.1] == "TP"
    assert labels[15.0] == "FP"


def test_comparison_row_totals_across_files() -> None:
    row = ComparisonRow(
        label="테스트",
        params={},
        per_file={
            "a": evaluate([1.0, 2.0], [1.0]),          # TP1 FN1
            "b": evaluate([5.0], [5.0, 9.0]),          # TP1 FP1
        },
    )
    total = row.total
    assert (total.tp, total.fp, total.fn) == (2, 1, 1)


def test_format_comparison_includes_numbers() -> None:
    rows = [
        ComparisonRow(
            label="height=5",
            params={"height_db": 5},
            per_file={"파일럿_004.WAV": evaluate([1.0, 2.0], [1.0])},
        )
    ]
    text = format_comparison(rows, file_order=["파일럿_004.WAV"])
    assert "height=5" in text
    assert "1/0/1" in text  # TP/FP/FN
    assert "50.0%" in text  # Recall


def test_format_comparison_empty() -> None:
    assert "없습니다" in format_comparison([], file_order=[])
