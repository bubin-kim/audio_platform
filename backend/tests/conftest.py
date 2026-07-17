"""pytest 공통 픽스처.

Repository 테스트는 인메모리 SQLite로 격리 실행한다(실제 DB·앱 서버 불필요).
API 통합 테스트(`client`)는 TestClient + DB/Storage override로 실행한다.
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.background.worker as worker_module
from app.api.deps import get_db, get_storage_dep
from app.core.database import Base
from app.hooks.events import (
    on_dataset_exported,
    on_processing_done,
    on_processing_failed,
    on_project_created,
    on_upload_complete,
)
import app.models  # noqa: F401  (모든 모델을 Base.metadata에 등록)
from app.main import app
from app.storage.local import LocalStorage

_ALL_HOOKS = (
    on_project_created,
    on_upload_complete,
    on_processing_done,
    on_processing_failed,
    on_dataset_exported,
)


@pytest.fixture(autouse=True)
def _isolated_hooks():
    """모든 테스트를 훅 구독자 0명 상태로 실행한다.

    개발자 .env에 Notion 키가 있어도(= main.py import 시 구독자가 등록돼도)
    기존 테스트가 외부 호출 없이 그대로 통과하게 하는 회귀 방지선(docs/07 §7).
    Notion 테스트는 이 픽스처 이후 명시적으로 subscribe 한다.
    """
    saved = {h: list(h._subscribers) for h in _ALL_HOOKS}
    for h in _ALL_HOOKS:
        h.clear()
    yield
    for h, subs in saved.items():
        h._subscribers = subs


@pytest.fixture
def db() -> Session:
    """인메모리 SQLite 세션. 테이블을 생성하고 FK를 켠다."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    """임시 디렉터리 기반 LocalStorage."""
    return LocalStorage(root=tmp_path / "data")


@pytest.fixture
def make_wav(tmp_path: Path) -> Callable[..., Path]:
    """합성 사인파 wav를 만들어 경로를 돌려주는 팩토리.

    사용: make_wav(duration_sec=10, sample_rate=8000, channels=1)
    """

    def _make(
        *,
        duration_sec: float = 10.0,
        sample_rate: int = 8000,
        channels: int = 1,
        subtype: str = "PCM_16",
        name: str = "test.wav",
    ) -> Path:
        n = int(round(duration_sec * sample_rate))
        t = np.linspace(0.0, duration_sec, n, endpoint=False)
        wave = 0.2 * np.sin(2 * np.pi * 220.0 * t).astype(np.float32)
        data = wave if channels == 1 else np.column_stack([wave] * channels)
        path = tmp_path / name
        sf.write(str(path), data, sample_rate, subtype=subtype)
        return path

    return _make


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Job이 관여하는 통합 테스트용 TestClient.

    background/worker.py는 요청의 DI(get_db/get_storage_dep)를 거치지 않고 자체
    세션·get_storage()를 직접 호출하므로(BackgroundTasks는 DI 밖에서 실행), 여기서
    worker 모듈의 SessionLocal/get_storage도 같은 인메모리 DB·임시 Storage로 바꿔준다.
    """
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
    original_session_local = worker_module.SessionLocal
    original_get_storage = worker_module.get_storage
    worker_module.SessionLocal = TestSession
    worker_module.get_storage = lambda: storage
    with TestClient(app) as c:
        c._storage = storage
        c._session_factory = TestSession  # 레거시 데이터 직접 삽입용 (API 검증 우회)
        yield c
    worker_module.SessionLocal = original_session_local
    worker_module.get_storage = original_get_storage
    app.dependency_overrides.clear()


def upload_file(client: TestClient, project_id: int, wav: Path, name: str) -> dict:
    """테스트 헬퍼: 단일 wav 업로드 후 UploadResult(dict)를 돌려준다."""
    with wav.open("rb") as f:
        r = client.post(
            "/api/uploads",
            data={"project_id": project_id},
            files={"files": (name, f, "audio/wav")},
        )
    assert r.status_code == 201, r.text
    return r.json()
