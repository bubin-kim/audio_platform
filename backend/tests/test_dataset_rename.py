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


def test_create_and_rename_write_folder_hint(client: TestClient, tmp_path: Path) -> None:
    """생성·재명명 시 uploads/segments 폴더에 안내 파일이 남는다 (docs/17 §2l).

    File Station에서 폴더명을 직접 rename하면 DB의 storage_path와 어긋나
    waveform/spectrogram이 깨지는 사고가 있었다 — 폴더명 자체는 절대 안
    바꾸고, 안내 파일로만 사람이 알아보게 한다.
    """
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    ds = client.post(f"/api/projects/{pid}/datasets", json={"name": "1일차"}).json()
    ds_id = ds["id"]

    for prefix in ("uploads", "segments"):
        hint = tmp_path / "data" / prefix / str(ds_id) / "_dataset_info.txt"
        assert hint.exists(), f"{prefix}/{ds_id}/_dataset_info.txt 가 생성되지 않았다"
        text = hint.read_text(encoding="utf-8")
        assert "1일차" in text
        assert "폴더명을 직접 바꾸지 마세요" in text

    client.patch(f"/api/datasets/{ds_id}", json={"name": "본녹음 1일차"})
    for prefix in ("uploads", "segments"):
        hint = tmp_path / "data" / prefix / str(ds_id) / "_dataset_info.txt"
        assert "본녹음 1일차" in hint.read_text(encoding="utf-8")
