"""silence_based 커팅 전략 테스트.

합성 wav(소리-무음-소리 패턴)로 경계 검출·padding·min/max 조각 길이·
엣지 케이스(무음 없음, 전부 무음, 빈 params)를 검증한다.
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.audio.cutting import available_strategies, get_strategy

SR = 8000
TONE_AMP = 0.3  # ≈ -10.5 dBFS (기본 threshold -40보다 훨씬 큼)


def _tone(duration_sec: float, freq: float = 440.0) -> np.ndarray:
    t = np.linspace(0, duration_sec, int(duration_sec * SR), endpoint=False)
    return (TONE_AMP * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _silence(duration_sec: float) -> np.ndarray:
    return np.zeros(int(duration_sec * SR), dtype=np.float32)


def _write(tmp_path: Path, *parts: np.ndarray) -> Path:
    path = tmp_path / "synth.wav"
    sf.write(path, np.concatenate(parts), SR, subtype="PCM_16")
    return path


def test_registered() -> None:
    assert "silence_based" in available_strategies()


def test_two_events_split_at_silence(tmp_path: Path) -> None:
    # 1초 소리 - 0.5초 무음 - 1초 소리 → 2조각
    path = _write(tmp_path, _tone(1.0), _silence(0.5), _tone(1.0))
    segs = list(get_strategy("silence_based").cut(path, {}))
    assert len(segs) == 2
    assert [s.index for s in segs] == [0, 1]
    # 첫 조각: 0부터 시작해 소리 끝(1.0초) + padding(0.1초) 근처에서 끝난다.
    assert segs[0].start_sec == 0.0
    assert segs[0].end_sec == pytest.approx(1.1, abs=0.05)
    # 둘째 조각: 소리 시작(1.5초) - padding 근처에서 시작한다.
    assert segs[1].start_sec == pytest.approx(1.4, abs=0.05)
    assert segs[1].end_sec == pytest.approx(2.5, abs=0.05)
    # 샘플 수와 (start,end)가 일치(저장 시 duration 계산의 근거).
    for s in segs:
        assert len(s.samples) == pytest.approx((s.end_sec - s.start_sec) * SR, abs=1)


def test_short_silence_does_not_split(tmp_path: Path) -> None:
    # 무음 0.1초 < min_silence_sec 0.3 → 한 덩어리
    path = _write(tmp_path, _tone(0.5), _silence(0.1), _tone(0.5))
    segs = list(get_strategy("silence_based").cut(path, {}))
    assert len(segs) == 1


def test_min_segment_drops_blip(tmp_path: Path) -> None:
    # 0.05초 스파이크는 min_segment_sec(0.2) 미만 → 버려지고 뒤 소리만 남는다
    path = _write(tmp_path, _tone(0.05), _silence(0.5), _tone(1.0))
    segs = list(get_strategy("silence_based").cut(path, {}))
    assert len(segs) == 1
    assert segs[0].index == 0  # 버려진 조각은 순번을 차지하지 않는다
    assert segs[0].start_sec == pytest.approx(0.45, abs=0.05)


def test_all_silence_yields_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path, _silence(2.0))
    assert list(get_strategy("silence_based").cut(path, {})) == []


def test_no_silence_yields_whole_file(tmp_path: Path) -> None:
    path = _write(tmp_path, _tone(2.0))
    segs = list(get_strategy("silence_based").cut(path, {}))
    assert len(segs) == 1
    assert segs[0].start_sec == 0.0
    assert segs[0].end_sec == pytest.approx(2.0, abs=0.05)


def test_max_segment_force_splits(tmp_path: Path) -> None:
    # 무음 없는 3.2초 소리 + max 1.0초 → 1.0/1.0/1.0/0.2초 → min_segment(0.2) 통과 4조각
    path = _write(tmp_path, _tone(3.2))
    segs = list(
        get_strategy("silence_based").cut(path, {"max_segment_sec": 1.0})
    )
    assert len(segs) == 4
    assert all(s.duration_sec <= 1.0 + 1e-6 for s in segs[:3])
    # 강제 분할 지점은 이어져야 한다(겹침·구멍 없음).
    for prev, cur in zip(segs, segs[1:]):
        assert cur.start_sec == pytest.approx(prev.end_sec, abs=1e-6)


def test_threshold_respected(tmp_path: Path) -> None:
    # 조용한 톤(-52dBFS)은 threshold -40에서는 무음 취급 → 조각 없음.
    quiet = (0.0025 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, SR, endpoint=False))).astype(
        np.float32
    )
    path = tmp_path / "quiet.wav"
    sf.write(path, quiet, SR, subtype="PCM_16")
    assert list(get_strategy("silence_based").cut(path, {})) == []
    # threshold를 -60으로 낮추면 소리로 인정된다.
    segs = list(
        get_strategy("silence_based").cut(path, {"silence_threshold_db": -60.0})
    )
    assert len(segs) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"silence_threshold_db": 3},  # 음수가 아님
        {"min_silence_sec": 0},
        {"min_segment_sec": -1},
        {"padding_sec": -0.1},
        {"max_segment_sec": 0.1},  # min_segment(기본 0.2)보다 작음
        {"silence_threshold_db": "loud"},  # 숫자가 아님
    ],
)
def test_invalid_params_raise(tmp_path: Path, params: dict) -> None:
    path = _write(tmp_path, _tone(0.5))
    with pytest.raises(ValueError):
        list(get_strategy("silence_based").cut(path, params))
