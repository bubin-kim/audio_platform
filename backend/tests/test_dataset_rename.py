"""PATCH /api/datasets/{id} — 데이터셋 이름 변경.

여러 원본 파일을 한 Dataset에 몰아넣은 뒤 구분용으로 재명명하는 시나리오
(실제로 겪은 상황: 300초 업로드 제약을 피해 원본을 분할 업로드하면서
서로 다른 파일 4개가 같은 Dataset에 섞여 이름 정리가 필요했다).
"""

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
        yield c
    app.dependency_overrides.clear()


def _project_payload() -> dict:
    return {
        "name": "탐지 시험",
        "domain": "vehicle",
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 3.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [],
    }


def test_rename_dataset(client: TestClient) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    ds = client.post(f"/api/projects/{pid}/datasets", json={"name": "260819_034"}).json()

    r = client.patch(f"/api/datasets/{ds['id']}", json={"name": "본녹음 샘플 모음"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "본녹음 샘플 모음"

    # 목록 조회에도 새 이름이 반영돼야 한다
    listed = client.get(f"/api/projects/{pid}/datasets").json()["items"]
    assert listed[0]["name"] == "본녹음 샘플 모음"


def test_rename_dataset_not_found(client: TestClient) -> None:
    r = client.patch("/api/datasets/999", json={"name": "x"})
    assert r.status_code == 404


def test_rename_dataset_rejects_empty_name(client: TestClient) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    ds = client.post(f"/api/projects/{pid}/datasets", json={"name": "원래이름"}).json()

    r = client.patch(f"/api/datasets/{ds['id']}", json={"name": ""})
    assert r.status_code == 422
