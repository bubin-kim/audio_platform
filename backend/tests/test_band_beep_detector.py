"""band_beep_detector 테스트 — 대역통과 기반 비프음 onset 검출.

합성 신호(저역 배경잡음 + 1900~2100Hz 톤 10개, 매 10초 간격)로 계약을
검증한다. 실제 216개 원본에 대한 성능은 별도로 사람이 확인한다(라벨
저장 없는 표시 전용 기능이라 GT 파이프라인에 편입하지 않음).
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy import signal

from app.audio.band_beep_detector import DEFAULTS, detect_beep_onsets, validate_params
from app.audio.verify_onsets import summarize_onsets

SR = 48000


def _make_file(
    tmp_path: Path,
    onset_times: list[float],
    duration: float = 100.0,
    noise_amp: float = 0.3,
    tone_hz: float = 2000.0,
    tone_dur: float = 0.2,
    name: str = "synth_beep.wav",
) -> Path:
    """저역 배경잡음 + 지정 위치의 짧은 톤(비프음)으로 합성 파일을 만든다.

    배경은 event_detection 테스트와 같은 이유로 저역통과 소음을 쓴다 —
    백색잡음은 대역통과 필터를 거쳐도 프레임마다 요동해 오탐을 유발한다
    (실측: k=5 기준 오탐 25개 vs k=8 기준 2개, 파일 경계뿐).
    """
    rng = np.random.default_rng(42)
    n = int(duration * SR)
    raw = rng.normal(0, 1.0, n)
    sos_lp = signal.butter(4, 500, btype="lowpass", fs=SR, output="sos")
    y = (signal.sosfilt(sos_lp, raw) * noise_amp).astype(np.float64)

    t = np.arange(n) / SR
    for onset in onset_times:
        mask = (t >= onset) & (t < onset + tone_dur)
        y[mask] += 0.3 * np.sin(2 * np.pi * tone_hz * t[mask])

    y = (y / np.max(np.abs(y))).astype(np.float32)
    path = tmp_path / name
    sf.write(str(path), y, SR, subtype="PCM_16")
    return path


ONSET_TIMES = [5.0, 15.0, 25.0, 35.0, 45.0, 55.0, 65.0, 75.0, 85.0, 95.0]


def test_detects_all_ten_beeps(tmp_path: Path) -> None:
    """매 10초 간격 비프음 10개를 tolerance 0.5초 이내로 전부 찾는다."""
    wav = _make_file(tmp_path, ONSET_TIMES)
    onsets = detect_beep_onsets(wav, {})

    for expected in ONSET_TIMES:
        assert any(abs(d - expected) < 0.5 for d in onsets), (
            f"{expected}초 근방 비프음을 못 찾음: {onsets}"
        )


def test_no_boundary_false_positives(tmp_path: Path) -> None:
    """전역 하한(k_global) 덕에 파일 맨앞·맨끝 오탐이 나오지 않는다.

    지역 임계값만 쓰던 때는 median_filter(mode="nearest")가 경계에서
    가장자리 값을 복제해 지역 MAD가 0에 가까워지고, 진짜 신호의 1/5
    크기인 잡음도 통과해 앞뒤로 오탐 2개가 났다(실측). 전역 하한을
    함께 걸어 정확히 10개만 남는다.
    """
    wav = _make_file(tmp_path, ONSET_TIMES)
    onsets = detect_beep_onsets(wav, {})
    assert len(onsets) == 10, f"경계 오탐이 섞였다: {onsets}"


def test_k_global_zero_disables_floor(tmp_path: Path) -> None:
    """k_global=0이면 전역 하한이 꺼져 경계 오탐이 다시 나타난다.

    단, 순음성 필터(tonality_db)가 켜져 있으면 그 오탐을 대신 걸러주므로
    두 방어를 모두 꺼야 차이가 드러난다 — 두 필터가 독립적으로 동작함을
    함께 확인하는 테스트다.
    """
    wav = _make_file(tmp_path, ONSET_TIMES)
    both_off = detect_beep_onsets(wav, {"k_global": 0, "tonality_db": 0})
    floor_only = detect_beep_onsets(wav, {"tonality_db": 0})
    assert len(both_off) > len(floor_only), (
        f"전역 하한이 경계 오탐을 못 막았다: {both_off} vs {floor_only}"
    )


def test_offset_consistency_via_summary(tmp_path: Path) -> None:
    """진짜 비프음의 오프셋(onset % 10)은 거의 일정해야 한다(녹음 설계)."""
    wav = _make_file(tmp_path, ONSET_TIMES)
    onsets = detect_beep_onsets(wav, {})
    summary = summarize_onsets(onsets)

    assert summary["count"] >= 10
    # 진짜 10개만 골라 오프셋을 직접 확인(경계 오탐은 배제) — 5초 근방에 몰려야 함
    true_positive_offsets = [
        round(d % 10, 3) for d in onsets if any(abs(d - e) < 0.5 for e in ONSET_TIMES)
    ]
    assert len(true_positive_offsets) == 10
    assert all(4.5 < off < 5.5 for off in true_positive_offsets), true_positive_offsets


def test_no_band_no_signal_returns_empty(tmp_path: Path) -> None:
    """대역이 나이퀴스트를 넘으면(샘플레이트가 너무 낮으면) 빈 리스트를 안전하게 반환한다."""
    wav = _make_file(tmp_path, ONSET_TIMES)
    onsets = detect_beep_onsets(wav, {"band_low_hz": 100000, "band_high_hz": 200000})
    assert onsets == []


def test_min_gap_prevents_split_peaks(tmp_path: Path) -> None:
    """min_gap_sec 안에서는 같은 비프음이 여러 피크로 쪼개지지 않는다."""
    wav = _make_file(tmp_path, [10.0])
    onsets = detect_beep_onsets(wav, {"min_gap_sec": 2.0})
    close_to_ten = [d for d in onsets if abs(d - 10.0) < 1.0]
    assert len(close_to_ten) == 1, f"하나의 비프음이 여러 피크로 쪼개짐: {onsets}"


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"band_low_hz": 2000, "band_high_hz": 1900}, "band_low_hz"),
        ({"k": 0}, "k"),
        ({"k_global": -1}, "k_global"),
        ({"tonality_win_sec": 0}, "tonality_win_sec"),
        ({"period_sec": -1}, "period_sec"),
        ({"period_search_sec": 0}, "period_search_sec"),
        ({"period_baseline_sec": 0}, "period_baseline_sec"),
        ({"min_gap_sec": -1}, "min_gap_sec"),
        ({"local_window_sec": 0}, "local_window_sec"),
        ({"smooth_ms": -5}, "smooth_ms"),
    ],
)
def test_validate_params_rejects_bad_values(overrides: dict, message: str) -> None:
    params = {**overrides}
    with pytest.raises(ValueError, match=message):
        validate_params(params)


def test_defaults_have_no_domain_branching() -> None:
    """DEFAULTS는 값만 있고, 도메인 분기 없이 함수 인자로만 쓰인다(P1)."""
    assert set(DEFAULTS.keys()) == {
        "band_low_hz",
        "band_high_hz",
        "k",
        "k_global",
        "tonality_db",
        "tonality_win_sec",
        "min_gap_sec",
        "local_window_sec",
        "smooth_ms",
        "period_sec",
        "period_search_sec",
        "period_baseline_sec",
        "offset_end_frac",
        "offset_max_sec",
        "offset_back_sec",
        "beam",
        "beam_step_deg",
        "beam_pattern",
    }


def test_periodic_mode_finds_weak_signal(tmp_path: Path) -> None:
    """주기 모드는 임계값 방식이 놓치는 약한 신호도 찾는다.

    실측(1일차 54개 전수 검증)에서 임계값 방식은 정상이 6개뿐이었다 —
    파일마다 신호 세기가 달라 진짜 비프음이 잡음 상위값보다 작은
    경우(분리 여유 0.25~0.84배)가 많았기 때문. 주기 누적은 임계값을
    쓰지 않고 "반복되는 위치"를 찾으므로 이런 신호도 잡는다.
    """
    # 임계값으로는 못 잡을 만큼 약한 신호(배경 대비 약간만 큼)
    wav = _make_file(tmp_path, ONSET_TIMES, noise_amp=0.5, name="weak.wav")

    threshold_mode = detect_beep_onsets(wav, {})
    periodic_mode = detect_beep_onsets(wav, {"period_sec": 10.0})

    # 주기 모드는 주기 수만큼(=10개) 항상 돌려준다
    assert len(periodic_mode) == 10
    # 그리고 위상이 일정하다 — 진짜 신호를 따라간다는 뜻
    offsets = [o % 10 for o in periodic_mode]
    assert float(np.std(offsets)) < 0.5, f"위상이 흔들림: {offsets}"
    # 임계값 모드보다 많이 찾거나 같아야 한다(이 신호에선 더 많이)
    assert len(periodic_mode) >= len(threshold_mode)


def test_periodic_mode_off_by_default() -> None:
    """period_sec 기본값은 0 — 주기를 모르는 데이터에는 켜지지 않는다."""
    assert DEFAULTS["period_sec"] == 0.0


def test_tonality_filter_rejects_broadband(tmp_path: Path) -> None:
    """광대역 소리(문 닫힘 같은 충격음)는 순음성 필터에 걸러진다.

    실제 주차장 녹음에서 엔벨로프만으로는 문 닫힘·차량 통과가 대역 안
    에너지를 튀게 해 오탐이 됐다(NAS 실데이터 100초에서 오탐 10개).
    좁은 대역 순음인지 스펙트럼으로 확인해 걸러낸다.
    """
    n = int(20.0 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(3)
    sos_lp = signal.butter(4, 500, btype="lowpass", fs=SR, output="sos")
    y = (signal.sosfilt(sos_lp, rng.normal(0, 1.0, n)) * 0.3).astype(np.float64)

    # 5초: 진짜 비프음(2000Hz 순음)
    m = (t >= 5.0) & (t < 5.2)
    y[m] += 0.3 * np.sin(2 * np.pi * 2000 * t[m])
    # 12초: 광대역 충격음(모든 주파수에 에너지 — 대역 안에서도 튄다)
    m2 = (t >= 12.0) & (t < 12.05)
    y[m2] += rng.normal(0, 1.5, m2.sum())

    y = (y / np.max(np.abs(y))).astype(np.float32)
    path = tmp_path / "broadband.wav"
    sf.write(str(path), y, SR, subtype="PCM_16")

    onsets = detect_beep_onsets(path, {})
    assert any(abs(o - 5.0) < 0.5 for o in onsets), f"진짜 비프음을 놓침: {onsets}"
    assert not any(abs(o - 12.0) < 0.5 for o in onsets), (
        f"광대역 충격음이 걸러지지 않음: {onsets}"
    )
