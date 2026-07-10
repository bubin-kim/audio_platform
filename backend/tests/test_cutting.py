"""cutting 테스트 — 전략 registry + FixedInterval + 저장 라운드트립."""

from collections.abc import Callable
from pathlib import Path

import pytest

from app.audio.cutting import available_strategies, get_strategy
from app.audio.io import write_wav
from app.audio.metadata import extract_metadata


def test_registry_lookup_and_available() -> None:
    assert "fixed_interval" in available_strategies()
    strat = get_strategy("fixed_interval")
    assert strat.name == "fixed_interval"


def test_unknown_strategy_raises() -> None:
    with pytest.raises(ValueError, match="알 수 없는 cutting_mode"):
        get_strategy("no_such_mode")


def test_fixed_interval_cuts_expected_segments(
    make_wav: Callable[..., Path],
) -> None:
    # 10초 / 3초 간격 → 3,3,3,1초 = 4조각
    path = make_wav(duration_sec=10.0, sample_rate=8000, channels=1)
    segs = list(get_strategy("fixed_interval").cut(path, {"interval_sec": 3.0}))
    assert len(segs) == 4
    # 순번·시작위치 검증
    assert [s.index for s in segs] == [0, 1, 2, 3]
    assert segs[0].start_sec == 0.0
    assert abs(segs[1].start_sec - 3.0) < 1e-6
    # 앞 3개는 3초, 마지막은 1초
    assert all(abs(s.duration_sec - 3.0) < 1e-6 for s in segs[:3])
    assert abs(segs[3].duration_sec - 1.0) < 1e-6


def test_fixed_interval_drop_last_short(make_wav: Callable[..., Path]) -> None:
    path = make_wav(duration_sec=10.0, sample_rate=8000, channels=1)
    segs = list(
        get_strategy("fixed_interval").cut(
            path, {"interval_sec": 3.0, "drop_last_shorter_than_sec": 1.5}
        )
    )
    # 마지막 1초 조각은 버려짐 → 3조각
    assert len(segs) == 3


def test_invalid_params_raise(make_wav: Callable[..., Path]) -> None:
    path = make_wav(duration_sec=2.0)
    with pytest.raises(ValueError, match="interval_sec"):
        list(get_strategy("fixed_interval").cut(path, {"interval_sec": 0}))
    with pytest.raises(ValueError, match="interval_sec"):
        list(get_strategy("fixed_interval").cut(path, {}))


def test_cut_then_write_roundtrip(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    # 커팅한 조각을 저장하고 다시 메타 추출 → 값이 맞는지
    path = make_wav(duration_sec=6.0, sample_rate=8000, channels=1)
    segs = list(get_strategy("fixed_interval").cut(path, {"interval_sec": 2.0}))
    assert len(segs) == 3
    out = tmp_path / "seg_000.wav"
    write_wav(out, segs[0].samples, segs[0].sample_rate)
    meta = extract_metadata(out)
    assert abs(meta.duration_sec - 2.0) < 1e-6
    assert meta.sample_rate == 8000
    assert meta.bit_depth == 16
