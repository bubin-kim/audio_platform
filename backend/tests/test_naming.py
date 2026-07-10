"""naming.py 테스트 — 파일명 생성 규칙 (audio/는 web 없이 단독 테스트)."""

import pytest

from app.audio.naming import pattern_fields, render_filename


def test_render_basic_with_seq_format() -> None:
    name = render_filename(
        "{date}_{model}_{distance}_{seq:03d}",
        {"date": "20260710", "model": "EV6", "distance": "10m", "seq": 1},
    )
    assert name == "20260710_EV6_10m_001.wav"


def test_extension_appended_and_respected() -> None:
    assert render_filename("{seq:02d}", {"seq": 5}).endswith(".wav")
    # 이미 확장자가 있으면 중복 안 붙임
    assert render_filename("clip_{seq}.wav", {"seq": 3}) == "clip_3.wav"


def test_different_domain_pattern() -> None:
    # 심음 도메인: 같은 코드, 다른 패턴/값 (재사용성)
    name = render_filename(
        "{patient_id}_{valve}_{seq:03d}",
        {"patient_id": "P01", "valve": "mitral", "seq": 12},
    )
    assert name == "P01_mitral_012.wav"


def test_missing_value_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="필요한 값이 없습니다"):
        render_filename("{date}_{seq:03d}", {"seq": 1})


def test_seq_format_type_mismatch_raises() -> None:
    # {seq:03d}에 문자열을 주면 명확한 에러
    with pytest.raises(ValueError):
        render_filename("{seq:03d}", {"seq": "abc"})


def test_illegal_chars_sanitized() -> None:
    name = render_filename("{label}_{seq:02d}", {"label": "a/b:c", "seq": 1})
    assert "/" not in name and ":" not in name
    assert name == "a_b_c_01.wav"


def test_pattern_fields_extraction() -> None:
    assert pattern_fields("{date}_{model}_{seq:03d}") == ["date", "model", "seq"]
    # 중복 제거
    assert pattern_fields("{a}_{a}_{b}") == ["a", "b"]
