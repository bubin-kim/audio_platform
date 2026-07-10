"""커팅 전략 인터페이스 + registry (재사용성의 엔진, 02 §5 / P1).

Service는 registry에서 전략을 조회해 그냥 호출한다. `if domain==...` 분기문이 코드에
절대 생기지 않는다. 새 커팅 방식은 이 파일을 건드리지 않고 파일 추가 + register만 한다.

전략은 **순수 파일 경로**를 받는다(Storage 종류를 모름). 결과는 SegmentAudio를 하나씩
yield → 대용량 파일에서도 한 조각씩만 메모리에 올릴 수 있다.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class SegmentAudio:
    """커팅으로 잘린 조각 하나 (아직 저장 전, 메모리 상 오디오)."""

    index: int  # 0-based 순번(파일명 seq에 쓰임)
    start_sec: float  # 원본에서 시작 위치(재현성)
    end_sec: float
    samples: np.ndarray  # (frames,) 또는 (frames, channels)
    sample_rate: int

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


class CutStrategy(ABC):
    """모든 커팅 전략의 공통 인터페이스."""

    #: registry 키 (Project.cutting_mode 값과 일치). 하위 클래스가 지정.
    name: str = ""

    @abstractmethod
    def cut(self, source: Path, params: dict[str, Any]) -> Iterator[SegmentAudio]:
        """원본 파일을 params에 따라 잘라 SegmentAudio를 순서대로 내보낸다."""

    def validate_params(self, params: dict[str, Any]) -> None:
        """params 유효성 검사(선택). 잘못되면 ValueError. 기본은 통과."""


# --- registry ---
_REGISTRY: dict[str, CutStrategy] = {}


def register_strategy(strategy: CutStrategy) -> CutStrategy:
    """전략 인스턴스를 registry에 등록한다. 전략 모듈이 import될 때 호출된다."""
    if not strategy.name:
        raise ValueError("전략에 name이 없습니다.")
    _REGISTRY[strategy.name] = strategy
    return strategy


def get_strategy(name: str) -> CutStrategy:
    """이름으로 전략을 조회한다. 없으면 사용 가능한 목록과 함께 ValueError."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"알 수 없는 cutting_mode='{name}'. 사용 가능: {available_strategies()}"
        ) from None


def available_strategies() -> list[str]:
    """등록된 전략 이름 목록."""
    return sorted(_REGISTRY)
