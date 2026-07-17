"""이벤트 훅 (확장 지점, P3/P4).

Service가 주요 사건 완료 시 여기 훅을 emit한다. MVP에는 구독자가 없다 —
"우체통만 설치하고 아무도 편지를 안 읽는" 상태(02 §7). V2에서 Notion/Drive가 subscribe한다.

핵심 로직은 훅의 구독자가 누구인지 모른다. 구독자에서 예외가 나도 본 흐름을 막지 않는다.
"""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class Hook:
    """이름 있는 이벤트 지점. 구독자 콜백을 모아 emit 시 순서대로 호출한다."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._subscribers: list[Callable[..., Any]] = []

    def subscribe(self, callback: Callable[..., Any]) -> None:
        self._subscribers.append(callback)

    def clear(self) -> None:
        """구독자 전부 해제. 테스트 격리용(운영 코드에서는 쓰지 않는다)."""
        self._subscribers.clear()

    def emit(self, **payload: Any) -> None:
        for callback in self._subscribers:
            try:
                callback(**payload)
            except Exception:  # noqa: BLE001 - 구독자 실패가 본 흐름을 깨선 안 됨
                logger.exception("hook '%s' 구독자 실행 실패", self.name)


# --- 훅 지점 (V2에서 hooks/notion.py 가 일부 구독) ---
on_project_created = Hook("on_project_created")  # V2-1 신설 (docs/07 §2)
on_upload_complete = Hook("on_upload_complete")
on_processing_done = Hook("on_processing_done")
on_processing_failed = Hook("on_processing_failed")  # V2-6 신설 (docs/14)
on_dataset_exported = Hook("on_dataset_exported")
