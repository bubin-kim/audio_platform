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


def _sanitize_component(value: str) -> str:
    """경로 구성요소 하나를 안전하게 만든다: 위험 문자·선행 점 → '_', 빈 값 → '_'."""
    safe = _ILLEGAL.sub("_", value).strip()
    safe = safe.lstrip(".")
    return safe or "_"


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


def render_path(pattern: str, values: dict[str, Any]) -> str:
    """경로 패턴을 값으로 채워 안전한 논리 경로를 만든다 (docs/11 §2).

    - 패턴의 `/`는 디렉터리 구분자로 유지된다.
    - 채워지는 **값 안의** 위험 문자(`/` 포함)는 `_`로 치환 — 값이 경로 구조를
      바꿀 수 없다 (예: 프로젝트명 "차량/A팀" → "차량_A팀").
    - 한글·공백은 유지. 필요한 값 누락은 명확한 ValueError.
    """
    safe_values = {
        key: _sanitize_component(value) if isinstance(value, str) else value
        for key, value in values.items()
    }
    try:
        rendered = pattern.format(**safe_values)
    except KeyError as exc:
        raise ValueError(
            f"경로 패턴에 필요한 값이 없습니다: {exc}. "
            f"필요 필드={pattern_fields(pattern)}"
        ) from exc
    except (ValueError, TypeError) as exc:
        raise ValueError(f"경로 패턴을 적용할 수 없습니다: {exc}") from exc

    parts = [part.strip() or "_" for part in rendered.split("/")]
    return "/".join(parts)
