"""커팅 전략 패키지.

전략 모듈을 여기서 import해 registry에 등록되게 한다.
새 전략 추가 = 이 폴더에 파일 추가 + 아래 import 한 줄. 다른 코드는 안 건드린다(P1).
"""

from app.audio.cutting.base import (
    CutStrategy,
    SegmentAudio,
    available_strategies,
    get_strategy,
    register_strategy,
)

# 전략 등록 (import 부수효과로 register_strategy 실행).
from app.audio.cutting import fixed_interval  # noqa: F401,E402

__all__ = [
    "CutStrategy",
    "SegmentAudio",
    "get_strategy",
    "available_strategies",
    "register_strategy",
]
