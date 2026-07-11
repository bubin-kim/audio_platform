"""Notion 이벤트 구독자 (V2-1 — docs/07_notion_integration.md).

프로젝트 생성 → Notion "프로젝트" DB에 row 생성.
커팅 완료 → 해당 프로젝트 페이지 본문에 요약 블록 append.

플러그인 원칙(P4): 토큰 미설정이면 register가 no-op — 이 파일과 main.py의 등록
2줄을 지우면 플랫폼은 MVP 상태로 완전 복귀한다. 핵심 로직은 이 모듈을 모른다.

구성: [1] HTTP 클라이언트 → [2] 비차단 실행 → [3] 구독자 → [4] 등록.
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal  # 모듈 심볼 (테스트 몽키패치용, worker와 동일)
from app.hooks.events import on_processing_done, on_project_created
from app.models.project import Project
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.segment_repo import SegmentRepository

logger = logging.getLogger(__name__)

NOTION_BASE_URL = "https://api.notion.com"

# 페이지 본문 섹션 (docs/07 §5.0). 컨테이너 탐색은 이 헤딩 텍스트로 매칭한다.
AUTO_LOG_HEADING = "자동 기록"
NOTES_HEADING = "연구 노트"


def _section_blocks() -> list[dict[str, Any]]:
    """페이지 본문의 두 섹션 블록: 자동 기록(토글 헤딩) + 연구 노트(사람 전용)."""
    return [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"🤖 {AUTO_LOG_HEADING} (플랫폼)"}}
                ],
                "is_toggleable": True,  # 자식을 가질 수 있는 토글 헤딩 = 로그 컨테이너
            },
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"📝 {NOTES_HEADING}"}}
                ]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": "여기에 자유롭게 기록하세요. 플랫폼은 이 영역을 건드리지 않습니다."},
                        "annotations": {"color": "gray"},
                    }
                ]
            },
        },
    ]


# --- [1] HTTP 클라이언트 — Notion API를 아는 유일한 곳 -------------------------


class NotionClient:
    """Notion REST API 최소 래퍼 (페이지 생성 / platform_id 조회 / 블록 append).

    transport는 테스트에서 httpx.MockTransport를 주입하기 위한 파라미터.
    """

    def __init__(
        self,
        *,
        api_key: str,
        database_id: str,
        api_version: str,
        timeout_sec: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.database_id = database_id
        self._client_kwargs: dict[str, Any] = {
            "base_url": NOTION_BASE_URL,
            "headers": {
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": api_version,
                "Content-Type": "application/json",
            },
            "timeout": timeout_sec,
        }
        if transport is not None:
            self._client_kwargs["transport"] = transport

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(**self._client_kwargs) as client:
            res = client.post(path, json=payload)
            res.raise_for_status()
            return res.json()

    def _patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(**self._client_kwargs) as client:
            res = client.patch(path, json=payload)
            res.raise_for_status()
            return res.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(**self._client_kwargs) as client:
            res = client.get(path, params=params)
            res.raise_for_status()
            return res.json()

    def create_project_page(self, project: Project) -> str:
        """프로젝트 row(=페이지)를 생성하고 page_id를 반환한다 (docs/07 §4·§5.1).

        본문에 §5.0의 두 섹션(자동 기록 컨테이너 + 연구 노트)을 함께 만든다.
        """
        properties: dict[str, Any] = {
            "프로젝트명": _title(project.name),
            "platform_id": _number(project.id),
            "파일명 규칙": _rich_text(project.naming_pattern),
            "생성일": _date(project.created_at),
        }
        if project.domain:
            properties["도메인"] = _select(project.domain)
        if project.cutting_mode:
            properties["커팅 모드"] = _select(project.cutting_mode)
        if project.target_duration_sec is not None:
            properties["목표 시간(초)"] = _number(project.target_duration_sec)

        data = self._post(
            "/v1/pages",
            {
                "parent": {"database_id": self.database_id},
                "properties": properties,
                "children": _section_blocks(),
            },
        )
        return data["id"]

    def find_log_container(self, page_id: str) -> str | None:
        """페이지 자식에서 '자동 기록' 토글 헤딩(로그 컨테이너)의 block_id를 찾는다.

        상단 100블록까지만 본다(컨테이너는 항상 페이지 상단 — docs/07 §5.0 한계 명시).
        """
        data = self._get(f"/v1/blocks/{page_id}/children", params={"page_size": 100})
        for block in data.get("results", []):
            if block.get("type") != "heading_2":
                continue
            texts = block.get("heading_2", {}).get("rich_text", [])
            plain = "".join(t.get("plain_text", "") for t in texts)
            if AUTO_LOG_HEADING in plain:
                return block["id"]
        return None

    def create_sections(self, page_id: str) -> str:
        """두 섹션을 페이지 끝에 생성하고 로그 컨테이너 block_id를 반환한다.

        구버전 페이지(섹션 없이 만들어진) 소급용 — 기존 본문은 건드리지 않는다.
        """
        data = self._patch(
            f"/v1/blocks/{page_id}/children", {"children": _section_blocks()}
        )
        for block in data.get("results", []):
            if block.get("type") == "heading_2" and block.get("heading_2", {}).get(
                "is_toggleable"
            ):
                return block["id"]
        raise RuntimeError("섹션 생성 응답에서 로그 컨테이너를 찾지 못했습니다.")

    def find_page_by_platform_id(self, project_id: int) -> str | None:
        """platform_id 속성으로 페이지를 찾아 page_id를 반환한다. 없으면 None."""
        data = self._post(
            f"/v1/databases/{self.database_id}/query",
            {
                "filter": {
                    "property": "platform_id",
                    "number": {"equals": project_id},
                },
                "page_size": 1,
            },
        )
        results = data.get("results", [])
        return results[0]["id"] if results else None

    def append_summary_block(
        self, container_id: str, text: str, detail: str | None = None
    ) -> None:
        """로그 컨테이너 안에 bullet 한 줄(+중첩 파라미터 줄)을 추가한다 (docs/07 §5.2).

        detail이 있으면 bullet의 자식 문단으로 붙는다(이번 Job의 cutting_params 등).
        """
        bullet: dict[str, Any] = {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            },
        }
        if detail:
            bullet["bulleted_list_item"]["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": detail},
                                "annotations": {"color": "gray"},
                            }
                        ]
                    },
                }
            ]
        self._patch(f"/v1/blocks/{container_id}/children", {"children": [bullet]})


# 속성 페이로드 빌더 (Notion property JSON 형태)
def _title(value: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _rich_text(value: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value}}]}


def _select(value: str) -> dict[str, Any]:
    return {"select": {"name": value}}


def _number(value: float | int) -> dict[str, Any]:
    return {"number": value}


def _date(value: datetime) -> dict[str, Any]:
    return {"date": {"start": value.isoformat()}}


def _format_cutting_params(job_params: dict[str, Any]) -> str | None:
    """Job.params → '모드 · key=value, ...' 한 줄. 키를 하드코딩하지 않는다(P1).

    어떤 전략(silence_based/fixed_interval/미래 전략)이 와도 dict를 그대로 펼친다.
    """
    mode = job_params.get("cutting_mode")
    cutting_params: dict[str, Any] = job_params.get("cutting_params") or {}
    if not mode and not cutting_params:
        return None
    rendered = ", ".join(f"{k}={v}" for k, v in cutting_params.items())
    return f"{mode} · {rendered}" if rendered else str(mode)


def _make_client() -> NotionClient:
    """설정으로 클라이언트 생성. 테스트에서 이 함수를 몽키패치한다."""
    settings = get_settings()
    return NotionClient(
        api_key=settings.notion_api_key,
        database_id=settings.notion_database_id,
        api_version=settings.notion_api_version,
        timeout_sec=settings.notion_timeout_sec,
    )


# --- [2] 비차단 실행 — 요청 경로를 Notion 지연이 막지 않게 ----------------------


def _spawn(target: Callable[..., None], **kwargs: Any) -> None:
    """데몬 스레드로 실행 (docs/07 §6). 테스트에서 동기 실행으로 몽키패치한다."""
    threading.Thread(target=target, kwargs=kwargs, daemon=True).start()


# --- [3] 구독자 — 훅 payload와 1:1, 실제 작업은 _log_* 가 스레드에서 ------------


def _handle_project_created(project_id: int) -> None:
    _spawn(_log_project_created, project_id=project_id)


def _log_project_created(project_id: int) -> None:
    """프로젝트 생성 → Notion row 생성. 실패는 로그만(본 흐름 보호)."""
    db = SessionLocal()
    try:
        project = ProjectRepository(db).get(project_id)
        if project is None:
            logger.warning("notion: Project %s 없음 — 기록 생략", project_id)
            return
        _make_client().create_project_page(project)
        logger.info("notion: 프로젝트 페이지 생성 (project_id=%s)", project_id)
    except Exception:  # noqa: BLE001 - 스레드 안이라 Hook.emit 보호 밖 → 자체 처리
        logger.exception("notion: 프로젝트 페이지 생성 실패 (project_id=%s)", project_id)
    finally:
        db.close()


def _handle_processing_done(dataset_id: int, job_id: int) -> None:
    _spawn(_log_processing_done, dataset_id=dataset_id, job_id=job_id)


def _log_processing_done(dataset_id: int, job_id: int) -> None:
    """커팅 완료 → 프로젝트 페이지 찾아(없으면 생성) 요약 블록 append."""
    db = SessionLocal()
    try:
        dataset = DatasetRepository(db).get(dataset_id)
        job = JobRepository(db).get(job_id)
        if dataset is None or job is None:
            logger.warning(
                "notion: Dataset %s / Job %s 없음 — 기록 생략", dataset_id, job_id
            )
            return
        project = dataset.project

        # 이번 커팅이 만든 세그먼트 수는 job.total_items, 총 길이는 dataset 세그먼트 합산.
        segments = SegmentRepository(db).all_for_dataset(dataset_id)
        total_duration = sum(s.duration_sec for s in segments)

        client = _make_client()
        page_id = client.find_page_by_platform_id(project.id)
        if page_id is None:
            # 연동 이전에 만든 프로젝트 — 첫 커팅 때 소급 생성 (docs/07 §5.2)
            page_id = client.create_project_page(project)

        # 로그 컨테이너(자동 기록 섹션) 확보 — 구버전 페이지면 섹션을 소급 생성.
        container_id = client.find_log_container(page_id)
        if container_id is None:
            container_id = client.create_sections(page_id)

        finished = job.finished_at or datetime.now(timezone.utc)
        text = (
            f"{finished.strftime('%Y-%m-%d %H:%M')} UTC — "
            f"세그먼트 {job.total_items}개, 총 {total_duration:.1f}초 "
            f"(dataset: {dataset.name}, Job #{job.id})"
        )
        client.append_summary_block(
            container_id, text, detail=_format_cutting_params(job.params)
        )
        logger.info("notion: 커팅 요약 기록 (dataset_id=%s, job_id=%s)", dataset_id, job_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "notion: 커팅 요약 기록 실패 (dataset_id=%s, job_id=%s)", dataset_id, job_id
        )
    finally:
        db.close()


# --- [4] 등록 ---------------------------------------------------------------


def register_notion_subscribers(settings: Settings | None = None) -> bool:
    """활성화 조건 충족 시 훅에 구독자를 등록한다. 등록 여부를 반환.

    토큰/DB id가 없으면 아무것도 하지 않는다(P4 — 없어도 완전 동작).
    """
    settings = settings or get_settings()
    if not settings.notion_enabled:
        logger.info("notion: 미설정 — 구독자 등록 생략 (플랫폼은 정상 동작)")
        return False
    on_project_created.subscribe(_handle_project_created)
    on_processing_done.subscribe(_handle_processing_done)
    logger.info("notion: 구독자 등록 완료 (project_created, processing_done)")
    return True
