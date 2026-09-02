"""verify_onsets.summarize_onsets 테스트 — 순수 통계 함수."""

from app.audio.verify_onsets import summarize_onsets


def test_summarize_regular_onsets() -> None:
    onsets = [5.0, 15.0, 25.0, 35.0]
    summary = summarize_onsets(onsets)

    assert summary["count"] == 4
    assert summary["offsets_sec"] == [5.0, 5.0, 5.0, 5.0]
    assert summary["offset_median_sec"] == 5.0
    assert summary["offset_stddev_sec"] == 0.0
    assert summary["gaps_sec"] == [10.0, 10.0, 10.0]


def test_summarize_empty() -> None:
    summary = summarize_onsets([])
    assert summary["count"] == 0
    assert summary["offsets_sec"] == []
    assert summary["offset_median_sec"] is None
    assert summary["offset_stddev_sec"] == 0.0
    assert summary["gaps_sec"] == []


def test_summarize_unsorted_input_is_sorted() -> None:
    summary = summarize_onsets([25.0, 5.0, 15.0])
    assert summary["onsets_sec"] == [5.0, 15.0, 25.0]
    assert summary["gaps_sec"] == [10.0, 10.0]


def test_summarize_scattered_offsets_has_nonzero_stddev() -> None:
    """오프셋이 흩어지면(=검출이 의심스러우면) 표준편차가 커야 한다."""
    onsets = [1.0, 15.0, 23.0, 39.0]  # 오프셋: 1, 5, 3, 9
    summary = summarize_onsets(onsets)
    assert summary["offset_stddev_sec"] > 1.0


def test_wraparound_phase_is_not_penalized() -> None:
    """위상이 0초 근처여도 규칙적이면 표준편차가 작아야 한다(원형 통계).

    일반 표준편차를 쓰면 0.04와 9.99가 정반대 값으로 계산돼 4.6초까지
    부풀려진다 — 실제로는 10초 간격으로 정확히 잡고 있는데 "흔들림"으로
    오판한다(1일차 54개 중 3개가 이 이유로 오판됐다).
    """
    # 위상 ~0초, 10초 간격으로 정확히 규칙적
    onsets = [0.04, 10.33, 20.64, 29.98, 40.64]
    summary = summarize_onsets(onsets)
    assert summary["offset_stddev_sec"] < 0.5, summary["offset_stddev_sec"]


def test_wraparound_and_midphase_give_similar_stddev() -> None:
    """같은 산포라면 위상 위치(0초 근처든 5초 근처든)와 무관하게 값이 비슷해야 한다."""
    near_zero = summarize_onsets([0.1, 9.9, 20.1, 29.9])  # ±0.1 산포, 위상 0
    near_five = summarize_onsets([5.1, 14.9, 25.1, 34.9])  # ±0.1 산포, 위상 5
    assert abs(near_zero["offset_stddev_sec"] - near_five["offset_stddev_sec"]) < 0.05
