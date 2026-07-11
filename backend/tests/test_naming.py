"""naming.py 테스트 — 파일명 생성 규칙 (audio/는 web 없이 단독 테스트)."""

import pytest

from app.audio.naming import pattern_fields, render_filename, render_path


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


# --- render_path (export 경로 패턴, docs/11 §2) ---


def test_render_path_basic_korean_preserved() -> None:
    path = render_path(
        "exports/{project}/{date}_{dataset}.csv",
        {"project": "심음데이터수집", "date": "20260712", "dataset": "v1 초기수집"},
    )
    assert path == "exports/심음데이터수집/20260712_v1 초기수집.csv"


def test_render_path_value_slash_cannot_change_structure() -> None:
    """값 안의 슬래시는 _로 — 값이 디렉터리 구조를 바꿀 수 없다."""
    path = render_path(
        "exports/{project}/{dataset}.csv",
        {"project": "차량/A팀", "dataset": "v1"},
    )
    assert path == "exports/차량_A팀/v1.csv"
    assert path.count("/") == 2  # 패턴의 슬래시만


def test_render_path_illegal_chars_sanitized() -> None:
    path = render_path("exports/{project}/x.csv", {"project": 'a:b*c?"d'})
    assert path == "exports/a_b_c__d/x.csv"


def test_render_path_missing_value_raises() -> None:
    with pytest.raises(ValueError, match="필요한 값이 없습니다"):
        render_path("exports/{project}/{date}.csv", {"project": "p"})


def test_render_path_numeric_values() -> None:
    path = render_path(
        "exports/{project_id}/{dataset_id}.csv", {"project_id": 3, "dataset_id": 5}
    )
    assert path == "exports/3/5.csv"
