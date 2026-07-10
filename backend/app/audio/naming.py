"""파일명 자동 생성 (F4).

Project.naming_pattern + 값(라벨 + 자동메타 + seq/date)으로 세그먼트 파일명을 만든다.
규칙은 설정에서 오고 코드는 포맷팅만 한다(P1). 순수 함수(웹·DB 모름).

예: pattern="{date}_{model}_{distance}_{seq:03d}", values={date:"20260710",
    model:"EV6", distance:"10m", seq:1} → "20260710_EV6_10m_001.wav"
"""

import re
import string
from typing import Any

_FORMATTER = string.Formatter()
# 파일명에 쓸 수 없는 문자 → '_'
_ILLEGAL = re.compile(r'[/\\:\*\?"<>\|\x00]')


def pattern_fields(pattern: str) -> list[str]:
    """패턴이 요구하는 필드명 목록(중복 제거, 등장 순서 유지).

    검증에 쓴다: 이 필드들이 values에 모두 있어야 렌더링이 성공한다.
    """
    seen: list[str] = []
    for _, field_name, _, _ in _FORMATTER.parse(pattern):
        if field_name and field_name not in seen:
            seen.append(field_name)
    return seen


def render_filename(
    pattern: str, values: dict[str, Any], *, extension: str = "wav"
) -> str:
    """패턴을 값으로 채워 안전한 파일명을 만든다.

    - `{seq:03d}` 같은 포맷 스펙 지원(값이 int여야 함).
    - 필요한 값 누락/타입 불일치는 명확한 ValueError로 알린다.
    - 경로 구분자 등 위험 문자는 '_'로 치환.
    """
    try:
        rendered = pattern.format(**values)
    except KeyError as exc:
        raise ValueError(
            f"naming_pattern에 필요한 값이 없습니다: {exc}. "
            f"필요 필드={pattern_fields(pattern)}"
        ) from exc
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"naming_pattern 포맷을 적용할 수 없습니다: {exc}"
        ) from exc

    safe = _ILLEGAL.sub("_", rendered).strip()
    if not safe:
        raise ValueError("생성된 파일명이 비어 있습니다.")

    ext = extension.lstrip(".").lower()
    if not safe.lower().endswith(f".{ext}"):
        safe = f"{safe}.{ext}"
    return safe
