"""event_detection 커팅 전략 테스트 (V2-9 — docs/17).

합성 신호로 계약을 검증한다. 실파일 성능(GT 대비 TP/FP/FN)은 사람이 만든
정답으로 별도 확인했다 — docs/17의 표 참조.

핵심 계약 세 가지:
  ① 알려진 위치의 이벤트를 찾는다
  ② 잘라낸 조각은 **원본 샘플**이다 (탐지에만 가공 신호를 쓴다)
  ③ 조각마다 탐지 근거(시점·튐 정도)를 남긴다
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.audio.cutting import get_strategy
from app.audio.cutting.event_detection import EventDetectionStrategy

SR = 44100
BAND = {"band_low_hz": 1900, "band_high_hz": 2100}


def _make_file(
    tmp_path: Path,
    event_times: list[float],
    duration: float = 40.0,
    noise_amp: float = 0.01,
    tone_hz: float = 2000.0,
    tone_amp: float = 0.3,
    name: str = "synth.wav",
    channels: int = 1,
) -> Path:
    """배경 소음 + 지정 위치의 톤 버스트(0.6초)로 합성 파일을 만든다.

    배경은 **저역 중심의 안정적인 소음**으로 만든다(실제 환경음처럼). 백색잡음을
    쓰면 탐지 대역에서 프레임마다 5~6dB씩 무작위로 요동해, 이벤트가 없어도
    임계를 넘는다(실측: 이벤트 0개인 백색잡음에서 5개 오탐). 알고리즘 문제가
    아니라 신호가 비현실적인 것이므로, 테스트 신호를 현실에 맞춘다.
    """
    rng = np.random.default_rng(42)
    n = int(duration * SR)
    raw = rng.normal(0, noise_amp, n)
    # 저역통과(이동평균)로 스펙트럼을 기울여 시간적으로 안정된 배경을 만든다
    kernel = np.ones(64) / 64
    y = np.convolve(raw, kernel, mode="same").astype(np.float32) * 4.0
    for t in event_times:
        a = int(t * SR)
        b = min(n, a + int(0.6 * SR))
        tt = np.arange(b - a) / SR
        y[a:b] += (tone_amp * np.sin(2 * np.pi * tone_hz * tt) * np.hanning(b - a)).astype(
            np.float32
        )
    data = np.stack([y] * channels, axis=1) if channels > 1 else y
    path = tmp_path / name
    sf.write(path, data, SR, subtype="PCM_16")
    return path


def test_registered_in_registry() -> None:
    """registry에 등록돼 Project.cutting_mode로 선택 가능해야 한다 (P1)."""
    assert isinstance(get_strategy("event_detection"), EventDetectionStrategy)


def test_detects_known_event_positions(tmp_path: Path) -> None:
    truth = [5.0, 13.0, 21.0, 29.0]
    wav = _make_file(tmp_path, truth)
    events = EventDetectionStrategy().detect_events(wav, {})
    found = [e.center_sec for e in events]
    matched = [t for t in truth if any(abs(t - f) <= 1.5 for f in found)]
    assert len(matched) == len(truth), f"검출 {[round(f,1) for f in found]}, 정답 {truth}"


def test_defaults_match_validated_parameters() -> None:
    """GT로 검증된 기본값이 바뀌면 성능이 달라진다 — 값을 고정해 회귀를 막는다."""
    from app.audio.cutting.event_detection import DEFAULTS

    assert DEFAULTS["height_db"] == 5.0
    assert DEFAULTS["min_gap_sec"] == 4.0
    assert DEFAULTS["before_sec"] == 3.0 and DEFAULTS["after_sec"] == 3.0
    assert DEFAULTS["channel"] == "mean"
    assert DEFAULTS["analysis_sr"] == 44100
    assert DEFAULTS["baseline_frames"] == 51


def test_cut_uses_before_after_window(tmp_path: Path) -> None:
    """조각은 [center-before, center+after] — 기본 3초씩이라 6초.

    합성 배경에서는 오탐이 섞일 수 있으므로 개수를 못 박지 않는다(실파일
    정확도는 GT로 따로 검증 — docs/17). 여기서 볼 것은 **창 크기 계약**이다.
    """
    wav = _make_file(tmp_path, [10.0, 20.0])
    segments = list(EventDetectionStrategy().cut(wav, {}))
    assert len(segments) >= 2

    for seg in segments:
        assert abs(seg.duration_sec - 6.0) < 0.2

    # 실제 이벤트(10초·20초)마다 그것을 감싸는 조각이 있어야 한다
    for truth in (10.0, 20.0):
        covering = [s for s in segments if s.start_sec <= truth <= s.end_sec]
        assert covering, f"{truth}초 이벤트를 담은 조각이 없다"
        # 이벤트가 조각 앞쪽 3초 부근에 놓인다 (pre_pad 계약)
        assert any(abs((truth - s.start_sec) - 3.0) < 1.5 for s in covering)


def test_cut_returns_original_samples_not_filtered(tmp_path: Path) -> None:
    """★ 커팅 결과는 원본 그대로여야 한다 (탐지에만 가공 신호를 쓴다).

    대역 밖 저주파를 크게 섞어두고, 잘린 조각에 그 성분이 남아 있는지 본다.
    밴드패스를 걸어 저장했다면 저주파가 사라진다.
    """
    n = int(30 * SR)
    t = np.arange(n) / SR
    low = 0.4 * np.sin(2 * np.pi * 120 * t)  # 대역(1900~2100) 밖
    y = low.astype(np.float32)
    a, b = int(15 * SR), int(15.6 * SR)
    tt = np.arange(b - a) / SR
    y[a:b] += (0.3 * np.sin(2 * np.pi * 2000 * tt) * np.hanning(b - a)).astype(np.float32)
    path = tmp_path / "mixed.wav"
    sf.write(path, y, SR, subtype="PCM_16")

    segments = list(EventDetectionStrategy().cut(path, {}))
    assert segments, "이벤트를 못 찾았다"
    clip = segments[0].samples.reshape(-1)
    spec = np.abs(np.fft.rfft(clip))
    freqs = np.fft.rfftfreq(len(clip), 1 / SR)
    low_energy = spec[(freqs > 100) & (freqs < 140)].max()
    band_energy = spec[(freqs > 1900) & (freqs < 2100)].max()
    assert low_energy > band_energy, "저주파가 깎였다 — 원본이 아니라 필터된 신호다"


def test_segments_carry_detection_metadata(tmp_path: Path) -> None:
    """조각마다 탐지 근거(원본명·시점·튐 정도)가 남아야 한다."""
    wav = _make_file(tmp_path, [12.0], name="alarm_src.wav")
    seg = next(iter(EventDetectionStrategy().cut(wav, {})))
    meta = seg.detection
    assert meta is not None
    assert meta["source_filename"] == "alarm_src.wav"
    assert abs(meta["detected_at_sec"] - 12.0) <= 1.5
    assert meta["prominence_db"] >= 5.0  # height_db 이상이라 검출된 것
    assert meta["band_hz"] == [1900.0, 2100.0]
    assert meta["channel"] == "mean"


def test_multichannel_uses_mean(tmp_path: Path) -> None:
    """4채널 입력도 처리되고, 잘린 조각은 원본 채널 수를 유지한다."""
    wav = _make_file(tmp_path, [10.0, 20.0], channels=4, name="multi.wav")
    segments = list(EventDetectionStrategy().cut(wav, {}))
    assert segments
    assert segments[0].samples.shape[1] == 4, "커팅은 원본(다채널) 그대로여야 한다"


def test_min_gap_prevents_double_detection(tmp_path: Path) -> None:
    """min_gap_sec보다 가까운 두 이벤트는 하나로 잡힌다 (알려진 한계)."""
    wav = _make_file(tmp_path, [10.0, 11.0])  # 1초 간격 < 기본 4초
    events = EventDetectionStrategy().detect_events(wav, {})
    near = [e for e in events if 8.0 <= e.center_sec <= 13.0]
    assert len(near) == 1, f"간격 4초 미만인데 분리됐다: {[e.center_sec for e in near]}"


def test_end_of_file_is_clipped_not_padded(tmp_path: Path) -> None:
    """파일 끝 이벤트는 파일 경계에서 잘린다 (없는 소리를 만들지 않는다)."""
    wav = _make_file(tmp_path, [38.5], duration=40.0)
    segments = list(EventDetectionStrategy().cut(wav, {}))
    assert segments
    for seg in segments:
        assert seg.end_sec <= 40.0 + 1e-6


def test_validate_params() -> None:
    strategy = EventDetectionStrategy()
    strategy.validate_params({})  # 전부 기본값이라 통과해야 한다

    with pytest.raises(ValueError, match="band_low_hz"):
        strategy.validate_params({"band_low_hz": 2500, "band_high_hz": 2000})
    with pytest.raises(ValueError, match="min_gap_sec"):
        strategy.validate_params({"min_gap_sec": 0})
    with pytest.raises(ValueError, match="baseline_frames"):
        strategy.validate_params({"baseline_frames": 2})
    with pytest.raises(ValueError, match="segment_sec"):
        strategy.validate_params({"segment_sec": 0})


def test_empty_file_yields_nothing(tmp_path: Path) -> None:
    path = tmp_path / "empty.wav"
    sf.write(path, np.zeros(0, dtype=np.float32), SR, subtype="PCM_16")
    assert list(EventDetectionStrategy().cut(path, {})) == []


# --- 프로젝트 생성 시점 파라미터 검증 (fail-fast) ---


def test_project_create_accepts_defaults(client) -> None:
    """파라미터를 비워도 검증된 기본값으로 생성된다."""
    r = client.post(
        "/api/projects",
        json={
            "name": "경보음 기본설정",
            "domain": None,
            "cutting_mode": "event_detection",
            "cutting_params": {},
            "naming_pattern": "{date}_{seq:03d}",
            "label_schema": [],
        },
    )
    assert r.status_code == 201


def test_project_create_rejects_invalid_band(client) -> None:
    r = client.post(
        "/api/projects",
        json={
            "name": "대역 뒤집힘",
            "domain": None,
            "cutting_mode": "event_detection",
            "cutting_params": {"band_low_hz": 2100, "band_high_hz": 1900},
            "naming_pattern": "{date}_{seq:03d}",
            "label_schema": [],
        },
    )
    assert r.status_code == 400
    assert "band_low_hz" in r.json()["detail"]


# --- 주기 재탐색 (선택 기능) ---


def test_periodic_rescue_off_by_default(tmp_path: Path) -> None:
    """기본은 꺼짐 — 불규칙한 도메인에서는 오탐만 늘기 때문."""
    from app.audio.cutting.event_detection import DEFAULTS

    assert DEFAULTS["periodic_rescue"] is False
    wav = _make_file(tmp_path, [8.0, 20.0, 32.0])
    assert all(not e.rescued for e in EventDetectionStrategy().detect_events(wav, {}))


def test_periodic_rescue_fills_grid_gap(tmp_path: Path) -> None:
    """규칙적 반복 중 비어 있는 격자 자리를 후보로 되살린다.

    합성 배경에서도 오탐이 섞이므로 "24초가 정확히 잡힌다"가 아니라
    **재탐색이 격자 빈 자리를 추가 후보로 올린다**는 계약을 검증한다.
    실파일 효과(FN 7→3)는 GT로 별도 확인 — docs/17.
    """
    # 배경을 아주 조용하게 해 1차 오탐을 줄인다
    times = [6.0, 12.0, 18.0, 30.0, 36.0]  # 24초 자리는 비어 있음
    rng = np.random.default_rng(7)
    n = int(45 * SR)
    raw = rng.normal(0, 0.002, n)
    y = (np.convolve(raw, np.ones(128) / 128, mode="same") * 6.0).astype(np.float32)
    for t in times:
        a = int(t * SR)
        b = min(n, a + int(0.6 * SR))
        tt = np.arange(b - a) / SR
        y[a:b] += (0.3 * np.sin(2 * np.pi * 2000 * tt) * np.hanning(b - a)).astype(
            np.float32
        )
    path = tmp_path / "periodic.wav"
    sf.write(path, y, SR, subtype="PCM_16")

    strategy = EventDetectionStrategy()
    base = strategy.detect_events(path, {})
    with_rescue = strategy.detect_events(path, {"periodic_rescue": True})

    rescued = [e for e in with_rescue if e.rescued]
    assert rescued, "재탐색이 아무 후보도 올리지 않았다"
    assert len(with_rescue) > len(base)
    # 되살린 후보는 1차 피크와 겹치지 않는다 (같은 자리를 두 번 세지 않는다)
    base_times = [e.center_sec for e in base]
    for r in rescued:
        assert all(abs(r.center_sec - b) > 1.0 for b in base_times)


def test_rescue_needs_enough_peaks(tmp_path: Path) -> None:
    """피크가 3개 미만이면 주기를 추정할 수 없으므로 그냥 넘어간다."""
    wav = _make_file(tmp_path, [10.0], duration=20.0)
    events = EventDetectionStrategy().detect_events(wav, {"periodic_rescue": True})
    assert all(not e.rescued for e in events)


def test_rescued_flag_in_metadata(tmp_path: Path) -> None:
    """건져낸 조각은 메타데이터로 구분된다 — 사람이 우선 확인할 수 있게."""
    wav = _make_file(tmp_path, [6.0, 12.0, 18.0, 24.0, 30.0])
    segments = list(
        EventDetectionStrategy().cut(wav, {"periodic_rescue": True})
    )
    assert segments
    assert all("rescued" in (s.detection or {}) for s in segments)
