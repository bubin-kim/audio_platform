"""업로드 파이프라인 통합 테스트 (TestClient + DB/Storage override).

실제 HTTP 요청으로 프로젝트 생성 → wav 업로드 → DB·Storage 반영을 검증한다.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_storage_dep
from app.core.database import Base
import app.models  # noqa: F401
from app.main import app
from app.storage.local import LocalStorage


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    # 요청 간 공유되는 인메모리 DB (StaticPool + 단일 연결).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    storage = LocalStorage(root=tmp_path / "data")

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_storage_dep] = lambda: storage
    with TestClient(app) as c:
        c._storage = storage  # 테스트에서 접근용
        c._session_factory = TestSession  # 레거시 데이터 직접 삽입용 (API 검증 우회)
        yield c
    app.dependency_overrides.clear()


def _project_payload() -> dict:
    return {
        "name": "차량음",
        "domain": "vehicle",
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 3.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [
            {"key": "distance_m", "type": "number", "required": True},
            {"key": "direction", "type": "enum", "options": ["N", "S", "E", "W"]},
        ],
        "target_duration_sec": 3600,
    }


def test_create_project_and_list(client: TestClient) -> None:
    r = client.post("/api/projects", json=_project_payload())
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["cutting_mode"] == "fixed_interval"

    r2 = client.get("/api/projects")
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["id"] == pid


def test_create_project_invalid_cutting_mode(client: TestClient) -> None:
    payload = _project_payload()
    payload["cutting_mode"] = "no_such_mode"
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 400
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_create_project_invalid_enum_schema(client: TestClient) -> None:
    payload = _project_payload()
    # enum 인데 options 없음 → 422 (Pydantic 검증)
    payload["label_schema"] = [{"key": "dir", "type": "enum"}]
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 422


def test_create_project_rejects_empty_enum_options(client: TestClient) -> None:
    """options:[''] 실사고 방어 (docs/12 C1) — 유효 옵션 0개·중복은 거부."""
    for bad_options in ([""], ["  "], ["N", "N"]):
        payload = _project_payload()
        payload["label_schema"] = [
            {"key": "dir", "type": "enum", "options": bad_options}
        ]
        r = client.post("/api/projects", json=payload)
        assert r.status_code == 422, f"options={bad_options}가 통과됨"


def test_create_project_filters_trailing_empty_option(client: TestClient) -> None:
    """'N,S,' 같은 쉼표 꼬리 입력은 거부가 아니라 정규화된다 (빈 옵션만 제거)."""
    payload = _project_payload()
    payload["label_schema"] = [
        {"key": "dir", "type": "enum", "options": ["N", ""], "required": False}
    ]
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 201
    assert r.json()["label_schema"][0]["options"] == ["N"]


def test_create_project_normalizes_enum_options(client: TestClient) -> None:
    """유효 옵션은 공백이 정리(strip)되어 저장된다."""
    payload = _project_payload()
    payload["label_schema"] = [
        {"key": "dir", "type": "enum", "options": [" N ", "S"], "required": False}
    ]
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 201
    assert r.json()["label_schema"][0]["options"] == ["N", "S"]


def test_upload_auto_creates_default_dataset(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=5.0, sample_rate=16000, name="rec.wav")

    with wav.open("rb") as f:
        r = client.post(
            "/api/uploads",
            data={"project_id": pid},
            files={"files": ("rec.wav", f, "audio/wav")},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created_dataset"] is True
    assert len(body["sources"]) == 1
    src = body["sources"][0]
    assert src["format"] == "wav"
    assert src["sample_rate"] == 16000
    assert abs(src["duration_sec"] - 5.0) < 1e-3

    # Storage에 실제 파일이 저장됐는지
    assert client._storage.exists(src["storage_path"])

    # Dataset 상세 조회 가능
    ds = client.get(f"/api/datasets/{body['dataset_id']}")
    assert ds.status_code == 200
    assert ds.json()["version"] == "v1"


def test_upload_reuses_dataset_second_time(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=2.0, name="a.wav")

    def _upload(name: str) -> dict:
        with wav.open("rb") as f:
            return client.post(
                "/api/uploads",
                data={"project_id": pid},
                files={"files": (name, f, "audio/wav")},
            ).json()

    first = _upload("a.wav")
    second = _upload("b.wav")
    # 두 번째는 같은 기본 Dataset을 재사용 (새로 만들지 않음)
    assert second["created_dataset"] is False
    assert second["dataset_id"] == first["dataset_id"]


def test_upload_unsupported_format_rejected(
    client: TestClient, tmp_path: Path
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    bad = tmp_path / "note.txt"
    bad.write_bytes(b"not audio")
    with bad.open("rb") as f:
        r = client.post(
            "/api/uploads",
            data={"project_id": pid},
            files={"files": ("note.txt", f, "text/plain")},
        )
    assert r.status_code == 400
    assert "지원하지 않는 포맷" in r.json()["detail"]


def test_upload_missing_project_404(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    wav = make_wav(duration_sec=1.0, name="x.wav")
    with wav.open("rb") as f:
        r = client.post(
            "/api/uploads",
            data={"project_id": 9999},
            files={"files": ("x.wav", f, "audio/wav")},
        )
    assert r.status_code == 404


def test_read_project_with_legacy_empty_enum_options(client: TestClient) -> None:
    """C1 검증 도입 전에 저장된 options:[''] 레거시 행도 조회는 500 없이 된다.

    입력(생성/수정)은 엄격하게 거부하되, 이미 DB에 있는 과거 데이터의 조회를
    막으면 안 된다 (실사고: /projects 전체가 500으로 죽음, 2026-07-13).
    """
    from app.models.project import Project

    session = client._session_factory()
    try:
        legacy = Project(
            name="레거시 심음",
            domain="heart",
            cutting_mode="fixed_interval",
            cutting_params={"interval_sec": 3},
            naming_pattern="{date}_{seq:03d}",
            label_schema=[
                {"key": "patient_id", "type": "string", "required": True, "options": None},
                {"key": "valve", "type": "enum", "required": False, "options": [""]},
            ],
        )
        session.add(legacy)
        session.commit()
        legacy_id = legacy.id
    finally:
        session.close()

    r = client.get("/api/projects")
    assert r.status_code == 200, r.text
    r2 = client.get(f"/api/projects/{legacy_id}")
    assert r2.status_code == 200, r2.text
    # 저장된 그대로 내려준다 (읽기는 관대 — 고치는 건 사용자가 설정 수정으로)
    assert r2.json()["label_schema"][1]["options"] == [""]


def test_upload_over_size_limit_413(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """업로드 총 크기 상한 (docs/13 §7) — 초과 시 413 + 안내 메시지."""
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.max_upload_mb
    settings.max_upload_mb = 0.01  # 10KB 상한으로 강제
    try:
        pid = client.post("/api/projects", json=_project_payload()).json()["id"]
        wav = make_wav(duration_sec=2.0, name="big.wav")  # 수십 KB > 상한
        with wav.open("rb") as f:
            r = client.post(
                "/api/uploads",
                data={"project_id": pid},
                files={"files": ("big.wav", f, "audio/wav")},
            )
        assert r.status_code == 413
        assert "상한" in r.json()["detail"]
    finally:
        settings.max_upload_mb = original
