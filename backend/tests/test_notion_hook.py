"""Notion 구독자 테스트 (V2-1 — docs/07 §7).

실제 HTTP 없이 httpx.MockTransport로 요청을 캡처해 URL·헤더·페이로드를 검증한다.
_spawn을 동기 실행으로 몽키패치해 스레드 타이밍 플레이크를 제거한다.
"""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.hooks.notion as notion_module
from app.core.config import Settings
from app.hooks.events import on_processing_done, on_project_created
from app.hooks.notion import NotionClient, register_notion_subscribers
from app.models.project import Project
from app.repositories.project_repo import ProjectRepository
from tests.conftest import upload_file

DB_ID = "0" * 32


def _container_block(block_id: str = "container-1") -> dict:
    """GET children 응답용: '자동 기록' 토글 헤딩(로그 컨테이너) 블록."""
    return {
        "id": block_id,
        "type": "heading_2",
        "heading_2": {
            "is_toggleable": True,
            "rich_text": [{"plain_text": "🤖 자동 기록 (플랫폼)"}],
        },
    }


class _Recorder:
    """MockTransport 핸들러 — 요청을 기록하고 시나리오별 응답을 돌려준다."""

    def __init__(
        self,
        *,
        query_results: list[dict] | None = None,
        page_children: list[dict] | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.query_results = query_results if query_results is not None else []
        # GET /v1/blocks/{page}/children 응답 (컨테이너 탐색용)
        self.page_children = page_children if page_children is not None else []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/pages":
            return httpx.Response(200, json={"id": "page-abc"})
        if path.endswith("/query"):
            return httpx.Response(200, json={"results": self.query_results})
        if "/blocks/" in path and request.method == "GET":
            return httpx.Response(200, json={"results": self.page_children})
        if "/blocks/" in path and request.method == "PATCH":
            # 섹션 생성이면 생성된 블록 목록을(컨테이너 포함), 로그 append면 빈 결과를 반환
            body = json.loads(request.content.decode())
            children = body.get("children", [])
            if any(c.get("type") == "heading_2" for c in children):
                return httpx.Response(
                    200, json={"results": [_container_block("container-new")]}
                )
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404, json={"message": "unknown path"})


def _client_with(recorder: _Recorder) -> NotionClient:
    return NotionClient(
        api_key="secret_test",
        database_id=DB_ID,
        api_version="2022-06-28",
        timeout_sec=5.0,
        transport=httpx.MockTransport(recorder),
    )


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content.decode())


# --- NotionClient 단위 테스트 (HTTP 페이로드 계약) ---


def test_create_project_page_payload(db: Session) -> None:
    project = ProjectRepository(db).add(
        Project(
            name="심음 판막별 수집",
            domain="heart",
            cutting_mode="fixed_interval",
            cutting_params={"interval_sec": 2.0},
            naming_pattern="{patient_id}_{seq:03d}",
            label_schema=[],
            target_duration_sec=1800.0,
        )
    )
    db.commit()

    rec = _Recorder()
    page_id = _client_with(rec).create_project_page(project)

    assert page_id == "page-abc"
    req = rec.requests[0]
    assert req.url.path == "/v1/pages"
    assert req.headers["Authorization"] == "Bearer secret_test"
    assert req.headers["Notion-Version"] == "2022-06-28"
    body = _body(req)
    assert body["parent"]["database_id"] == DB_ID
    props = body["properties"]
    assert props["프로젝트명"]["title"][0]["text"]["content"] == "심음 판막별 수집"
    assert props["platform_id"]["number"] == project.id
    assert props["도메인"]["select"]["name"] == "heart"
    assert props["커팅 모드"]["select"]["name"] == "fixed_interval"
    assert props["목표 시간(초)"]["number"] == 1800.0


def test_find_page_by_platform_id() -> None:
    rec = _Recorder(query_results=[{"id": "page-found"}])
    assert _client_with(rec).find_page_by_platform_id(7) == "page-found"
    body = _body(rec.requests[0])
    assert body["filter"] == {"property": "platform_id", "number": {"equals": 7}}

    rec_empty = _Recorder(query_results=[])
    assert _client_with(rec_empty).find_page_by_platform_id(7) is None


def test_append_summary_block_payload() -> None:
    rec = _Recorder()
    _client_with(rec).append_summary_block("page-abc", "요약 한 줄")
    req = rec.requests[0]
    assert req.url.path == "/v1/blocks/page-abc/children"
    assert req.method == "PATCH"
    block = _body(req)["children"][0]
    assert block["type"] == "bulleted_list_item"
    assert block["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "요약 한 줄"


# --- 등록 로직 ---


def _settings(**overrides) -> Settings:
    # .env를 읽지 않도록 필수값을 코드로 지정
    return Settings(_env_file=None, **overrides)


def test_register_noop_without_config() -> None:
    assert register_notion_subscribers(_settings()) is False
    assert len(on_project_created._subscribers) == 0
    assert len(on_processing_done._subscribers) == 0


def test_register_subscribes_when_configured() -> None:
    ok = register_notion_subscribers(
        _settings(notion_api_key="secret_x", notion_database_id=DB_ID)
    )
    assert ok is True
    assert len(on_project_created._subscribers) == 1
    assert len(on_processing_done._subscribers) == 1


# --- 구독자 E2E (TestClient + 구독 등록, 동기 _spawn, 가짜 클라이언트) ---


@pytest.fixture
def notion_env(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """구독자 등록 + _spawn 동기화 + 클라이언트/세션 교체가 끝난 테스트 환경.

    conftest의 _isolated_hooks가 구독자를 비운 뒤이므로 여기서 명시적으로 등록한다.
    client 픽스처가 worker 모듈의 SessionLocal을 교체하듯 notion 모듈도 교체한다.
    """
    monkeypatch.setattr(
        notion_module, "_spawn", lambda target, **kw: target(**kw)
    )
    # client 픽스처가 만든 인메모리 TestSession을 notion 모듈에도 연결
    import app.background.worker as worker_module

    monkeypatch.setattr(notion_module, "SessionLocal", worker_module.SessionLocal)

    rec = _Recorder()
    monkeypatch.setattr(notion_module, "_make_client", lambda: _client_with(rec))
    register_notion_subscribers(
        _settings(notion_api_key="secret_x", notion_database_id=DB_ID)
    )
    return rec


def _project_payload() -> dict:
    return {
        "name": "차량음",
        "domain": "vehicle",
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [],
    }


def test_project_create_triggers_notion_page(
    client: TestClient, notion_env: _Recorder
) -> None:
    r = client.post("/api/projects", json=_project_payload())
    assert r.status_code == 201
    paths = [req.url.path for req in notion_env.requests]
    assert paths == ["/v1/pages"]
    props = _body(notion_env.requests[0])["properties"]
    assert props["platform_id"]["number"] == r.json()["id"]


def test_processing_done_appends_summary_into_container(
    client: TestClient, notion_env: _Recorder, make_wav: Callable[..., Path]
) -> None:
    """커팅 완료 로그가 페이지 루트가 아니라 '자동 기록' 컨테이너 안에 붙는다."""
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=3.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]

    # 페이지 존재 + 섹션 있는 페이지 시나리오
    notion_env.query_results = [{"id": "page-abc"}]
    notion_env.page_children = [_container_block("container-1")]
    r = client.post(f"/api/datasets/{ds_id}/process")
    assert r.status_code == 202

    paths = [(req.method, req.url.path) for req in notion_env.requests]
    # [프로젝트 생성 페이지] → [query] → [GET children: 컨테이너 탐색] → [컨테이너에 append]
    assert paths == [
        ("POST", "/v1/pages"),
        ("POST", f"/v1/databases/{DB_ID}/query"),
        ("GET", "/v1/blocks/page-abc/children"),
        ("PATCH", "/v1/blocks/container-1/children"),  # ★ 페이지가 아닌 컨테이너
    ]
    bullet = _body(notion_env.requests[-1])["children"][0]["bulleted_list_item"]
    text = bullet["rich_text"][0]["text"]["content"]
    assert "세그먼트 3개" in text  # 3초 / 1초 간격
    assert "총 3.0초" in text
    assert "Job #" in text
    # ★ 중첩 파라미터 줄 (이번 Job의 cutting_params)
    detail = bullet["children"][0]["paragraph"]["rich_text"][0]["text"]["content"]
    assert detail == "fixed_interval · interval_sec=1.0"


def test_processing_done_lazy_creates_missing_page(
    client: TestClient, notion_env: _Recorder, make_wav: Callable[..., Path]
) -> None:
    """연동 이전 프로젝트 소급: query가 비면 페이지를 만들고 append까지 이어진다."""
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]

    notion_env.requests.clear()  # 생성 이벤트 기록 제거
    notion_env.query_results = []  # 페이지 없음 시나리오
    # 새로 만든 페이지에는 섹션이 있다(생성 시 children 포함)
    notion_env.page_children = [_container_block("container-1")]
    client.post(f"/api/datasets/{ds_id}/process")

    paths = [(req.method, req.url.path) for req in notion_env.requests]
    assert paths == [
        ("POST", f"/v1/databases/{DB_ID}/query"),
        ("POST", "/v1/pages"),  # lazy 페이지 생성 (섹션 포함)
        ("GET", "/v1/blocks/page-abc/children"),
        ("PATCH", "/v1/blocks/container-1/children"),
    ]


def test_processing_done_lazy_creates_sections_on_legacy_page(
    client: TestClient, notion_env: _Recorder, make_wav: Callable[..., Path]
) -> None:
    """구버전 페이지(섹션 없음) 소급: 섹션을 만들고 그 컨테이너에 기록한다."""
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]

    notion_env.requests.clear()
    notion_env.query_results = [{"id": "page-abc"}]  # 페이지는 있음
    notion_env.page_children = []  # 섹션 없음 (구버전)
    client.post(f"/api/datasets/{ds_id}/process")

    paths = [(req.method, req.url.path) for req in notion_env.requests]
    assert paths == [
        ("POST", f"/v1/databases/{DB_ID}/query"),
        ("GET", "/v1/blocks/page-abc/children"),  # 탐색 → 없음
        ("PATCH", "/v1/blocks/page-abc/children"),  # 섹션 소급 생성
        ("PATCH", "/v1/blocks/container-new/children"),  # 새 컨테이너에 기록
    ]


def test_create_page_includes_sections() -> None:
    """페이지 생성 시 본문에 두 섹션(자동 기록 토글 + 연구 노트)이 포함된다."""
    import app.hooks.notion as notion_module
    from app.models.project import Project as P

    rec = _Recorder()
    project = P(
        name="t", cutting_mode="fixed_interval", cutting_params={},
        naming_pattern="{seq}", label_schema=[],
    )
    project.id = 1
    from datetime import datetime, timezone
    project.created_at = datetime.now(timezone.utc)
    _client_with(rec).create_project_page(project)

    children = _body(rec.requests[0])["children"]
    types = [c["type"] for c in children]
    assert types == ["heading_2", "heading_2", "paragraph"]
    assert children[0]["heading_2"]["is_toggleable"] is True
    assert "자동 기록" in children[0]["heading_2"]["rich_text"][0]["text"]["content"]
    assert "연구 노트" in children[1]["heading_2"]["rich_text"][0]["text"]["content"]


def test_notion_failure_does_not_break_main_flow(
    client: TestClient, notion_env: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Notion이 500을 돌려줘도 프로젝트 생성 API는 정상 201 (docs/07 §6)."""

    def _boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "notion down"})

    monkeypatch.setattr(
        notion_module,
        "_make_client",
        lambda: NotionClient(
            api_key="k",
            database_id=DB_ID,
            api_version="2022-06-28",
            timeout_sec=5.0,
            transport=httpx.MockTransport(_boom),
        ),
    )
    r = client.post("/api/projects", json=_project_payload())
    assert r.status_code == 201  # 본 흐름은 멀쩡
