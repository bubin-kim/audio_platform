"""label_validation 단위 테스트 — is_labeled 판정 규칙."""

from app.services.label_validation import compute_is_labeled

SCHEMA = [
    {"key": "patient_id", "type": "string", "required": True},
    {"key": "valve", "type": "string", "required": True},
    {"key": "memo", "type": "string", "required": False},
]


def test_all_required_filled() -> None:
    assert compute_is_labeled(SCHEMA, {"patient_id": "P01", "valve": "mitral"}) is True


def test_missing_required_key() -> None:
    assert compute_is_labeled(SCHEMA, {"patient_id": "P01"}) is False


def test_empty_string_is_unfilled() -> None:
    """빈 문자열은 미충족 — 라벨링 진행률 왜곡 방지 (사용자 결정 2026-07-12)."""
    assert compute_is_labeled(SCHEMA, {"patient_id": "P01", "valve": ""}) is False


def test_whitespace_only_is_unfilled() -> None:
    assert compute_is_labeled(SCHEMA, {"patient_id": "P01", "valve": "   "}) is False


def test_falsy_but_valid_values_count_as_filled() -> None:
    """0·False는 유효한 라벨 값이다 (예: distance_m=0)."""
    schema = [
        {"key": "distance_m", "type": "number", "required": True},
        {"key": "verified", "type": "bool", "required": True},
    ]
    assert compute_is_labeled(schema, {"distance_m": 0, "verified": False}) is True


def test_optional_empty_does_not_block() -> None:
    """required가 아닌 필드는 비어 있어도 is_labeled에 영향 없음."""
    assert (
        compute_is_labeled(SCHEMA, {"patient_id": "P01", "valve": "mitral", "memo": ""})
        is True
    )
