"""라벨 검증 — Project.label_schema 기준으로 라벨 값을 검사한다.

커팅 시 common_labels(06_API.md §6.1)와 이후 개별 세그먼트 라벨 PATCH가 공유하는 규칙.
DB·web을 모르는 순수 함수 — 스키마(dict 리스트)와 값(dict)만 받는다.
"""

from typing import Any

from app.core.exceptions import ValidationError

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
}


def validate_labels(label_schema: list[dict[str, Any]], labels: dict[str, Any]) -> None:
    """제공된 라벨 값이 label_schema의 type/enum 규칙을 지키는지 검사한다. 위반 시 400.

    required 누락은 여기서 막지 않는다 — 부분 라벨링을 허용해야 대시보드의
    '라벨링 진행률'(is_labeled 비율, PRD F6 / 05 §4)이 의미를 가진다.
    required 충족 여부는 compute_is_labeled()가 is_labeled로 반영한다.
    """
    for field in label_schema:
        key = field["key"]
        if key not in labels or labels[key] is None:
            continue  # 누락은 is_labeled=False로 반영될 뿐, 에러가 아니다

        value = labels[key]
        field_type = field["type"]
        if field_type == "enum":
            options = field.get("options") or []
            if value not in options:
                raise ValidationError(
                    f"라벨 '{key}' 값 '{value}'은 허용된 옵션이 아닙니다. 허용: {options}"
                )
        else:
            check = _TYPE_CHECKS.get(field_type)
            if check and not check(value):
                raise ValidationError(
                    f"라벨 '{key}' 값 타입이 올바르지 않습니다. 기대: {field_type}, 받은 값: {value!r}"
                )


def compute_is_labeled(label_schema: list[dict[str, Any]], labels: dict[str, Any]) -> bool:
    """모든 required 필드가 채워졌는지로 is_labeled를 계산한다."""
    required_keys = [f["key"] for f in label_schema if f.get("required")]
    return all(labels.get(k) is not None for k in required_keys)
