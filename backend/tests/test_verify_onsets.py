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
