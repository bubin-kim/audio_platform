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
from scipy import signal

from app.audio.cutting import get_strategy
from app.audio.cutting.event_detection import EventDetectionStrategy

SR = 44100
BAND = {"band_low_hz": 1900, "band_high_hz": 2100}


def _make_file(
    tmp_path: Path,
    event_times: list[float],
    duration: float = 40.0,
    noise_amp: float = 0.05,
    tone_hz: float = 2000.0,
    tone_amp: float = 1.0,
    name: str = "synth.wav",
    channels: int = 1,
) -> Path:
    """배경 소음 + 지정 위치의 톤 버스트(0.6초)로 합성 파일을 만든다.

    배경은 **저역 중심의 안정적인 소음**으로 만든다(실제 환경음처럼). 백색잡음을
    쓰면 탐지 대역에서 프레임마다 5~6dB씩 무작위로 요동해, 이벤트가 없어도
    임계를 넘는다(실측: 이벤트 0개인 백색잡음에서 5개 오탐).

    **이동평균 필터를 쓰면 안 된다**: 64탭 이동평균은 SR/64=689Hz 배수마다
    널(null)이 있어 2000Hz 부근을 거의 통과시키지 않는다. 탐지 대역이 수치
    바닥에 놓여 요동이 이벤트보다 커지고, 실제로 심어둔 이벤트의 상승분이
    **음수**가 됐다(실측 -8.4dB). 그래도 테스트가 통과한 건 배경 오탐이
    우연히 정답 위치 1.5초 안에 떨어졌기 때문이다. butter 저역통과로 바꿔
    널을 없애고, 톤 진폭을 실측에 맞춘다 — 034 실측 상승분 +18.4dB 대비
    합성 +19.3dB(max)로 맞췄다.
    """
    rng = np.random.default_rng(42)
    n = int(duration * SR)
    raw = rng.normal(0, 1.0, n)
    b_lp, a_lp = signal.butter(4, 800 / (SR / 2), btype="low")
    y = (signal.lfilter(b_lp, a_lp, raw) * noise_amp).astype(np.float32)
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


def test_band_uses_max_not_mean(tmp_path: Path) -> None:
    """대역 집계는 **최대값**이어야 한다 — 평균으로 되돌리면 성능이 무너진다.

    근거(GT 004, 31개 정답, 파라미터 동일):
        평균 F1 77.4% (TP24/FP7/FN7) · 최대 F1 93.5% (TP29/FP2/FN2)
    본녹음 A/B 청취 판정에서도 평균이 단독 검출한 지점엔 경보음이 없었다.

    좁은 대역 톤을 넓은 대역(200Hz) 안에 두면, 평균은 신호를 주변 빈에
    희석시켜 상승분이 낮아진다. 그 차이를 직접 잰다.
    """
    wav = _make_file(tmp_path, [12.0])
    events = EventDetectionStrategy().detect_events(wav, {})
    hit = [e for e in events if abs(e.center_sec - 12.0) <= 1.5]
    assert hit, "최대값 집계인데도 심어둔 이벤트를 못 찾았다"

    # 같은 신호를 평균으로 집계하면 상승분이 눈에 띄게 작아야 한다
    import numpy as _np
    import soundfile as _sf
    from scipy import signal as _sig

    y, sr = _sf.read(str(wav), dtype="float32", always_2d=True)
    mono = y.mean(axis=1)
    freqs, times, zxx = _sig.stft(mono, sr, nperseg=2048, noverlap=1024)
    db = 20 * _np.log10(_np.abs(zxx) + 1e-10)
    m = (freqs >= 1900) & (freqs <= 2100)
    i = int(12.0 / float(times[1] - times[0]))
    by_max = db[m, i : i + 3].max()
    by_mean = db[m, i : i + 3].mean(axis=0).max()
    assert by_max > by_mean + 5.0, (
        f"대역 최대({by_max:.1f}dB)가 평균({by_mean:.1f}dB)보다 충분히 커야 한다"
    )


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

    # 파일 시작/끝에 걸린 조각은 잘려서 6초보다 짧다 (start_sec=0 등) — 정상.
    # 창 크기 계약은 양끝에 안 걸린 조각으로 확인한다.
    interior = [s for s in segments if s.start_sec > 0.0]
    assert interior, "양끝에 안 걸린 조각이 없다"
    for seg in interior:
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
    segments = list(EventDetectionStrategy().cut(wav, {}))
    assert segments, "이벤트를 못 찾았다"

    # 배경 요동으로 오탐이 앞에 섞일 수 있으므로 "첫 조각"을 가정하지 않고
    # 심어둔 이벤트를 담은 조각을 찾는다 (실제 녹음 034도 배경 diff가
    # 최대 15.2dB까지 튄다 — 오탐 자체는 정상이고 검수로 걸러진다)
    hit = [s for s in segments if abs(s.detection["detected_at_sec"] - 12.0) <= 1.5]
    assert hit, (
        "12.0초 이벤트를 담은 조각이 없다 — 검출 "
        f"{[round(s.detection['detected_at_sec'], 1) for s in segments]}"
    )
    meta = hit[0].detection
    assert meta is not None
    assert meta["source_filename"] == "alarm_src.wav"
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


def test_preserves_original_bit_depth(tmp_path: Path) -> None:
    """24bit 원본은 24bit 조각으로 잘려야 한다.

    16bit로 떨어뜨리면 약한 신호(파일럿 경보음 수준)에서 양자화 여유가
    44dB까지 줄어든다 — 실측. 원본 해상도를 유지한다.
    """
    n = int(20 * SR)
    rng = np.random.default_rng(11)
    y = (np.convolve(rng.normal(0, 0.01, n), np.ones(64) / 64, mode="same") * 4).astype(
        np.float32
    )
    for t in (6.0, 13.0):
        a = int(t * SR)
        b = a + int(0.6 * SR)
        tt = np.arange(b - a) / SR
        y[a:b] += (0.3 * np.sin(2 * np.pi * 2000 * tt) * np.hanning(b - a)).astype(
            np.float32
        )
    path = tmp_path / "src24.wav"
    sf.write(path, y, SR, subtype="PCM_24")

    segments = list(EventDetectionStrategy().cut(path, {}))
    assert segments, "이벤트를 못 찾았다"
    assert segments[0].subtype == "PCM_24"
