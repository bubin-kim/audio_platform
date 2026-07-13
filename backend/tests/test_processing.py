"""Processing/Job 파이프라인 테스트 (M6).

- ProcessingService 단위 테스트: 검증(400)·충돌(409) 규칙.
- API 통합 테스트: 업로드 → 커팅 Job 시작 → 백그라운드 실행 → 완료 상태·Segment 생성 확인.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.models.dataset import Dataset
from app.models.job import Job
from app.models.project import Project
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.project_repo import ProjectRepository
from app.schemas.job import ProcessRequest
from app.services.processing_service import ProcessingService
from tests.conftest import upload_file


def _project_payload() -> dict:
    return {
        "name": "차량음",
        "domain": "vehicle",
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{distance_m}_{seq:03d}",
        "label_schema": [
            {"key": "distance_m", "type": "number", "required": True},
        ],
        "target_duration_sec": 3600,
    }


# --- ProcessingService 단위 테스트 (인메모리 DB, worker 실행 없음) ---


def _make_project(db: Session) -> Project:
    return ProjectRepository(db).add(
        Project(
            name="차량음",
            domain="vehicle",
            cutting_mode="fixed_interval",
            cutting_params={"interval_sec": 1.0},
            naming_pattern="{date}_{seq:03d}",
            label_schema=[{"key": "distance_m", "type": "number", "required": True}],
        )
    )


def test_start_cutting_missing_dataset_404(db: Session) -> None:
    with pytest.raises(Exception) as exc_info:
        ProcessingService(db).start_cutting(999, ProcessRequest())
    assert "찾을 수 없습니다" in str(exc_info.value)


def test_start_cutting_invalid_common_labels_400(db: Session) -> None:
    """제공된 값의 type 위반은 400. (required 누락은 에러가 아님 — is_labeled로 반영)"""
    p = _make_project(db)
    d = DatasetRepository(db).add(Dataset(project_id=p.id, name="v1"))
    db.commit()
    with pytest.raises(ValidationError):
        ProcessingService(db).start_cutting(
            d.id, ProcessRequest(common_labels={"distance_m": "십미터"})
        )


def test_start_cutting_conflict_when_already_running(db: Session) -> None:
    p = _make_project(db)
    d = DatasetRepository(db).add(Dataset(project_id=p.id, name="v1"))
    db.flush()
    from app.repositories.job_repo import JobRepository
    from app.repositories.source_file_repo import SourceFileRepository
    from app.models.source_file import SourceFile

    SourceFileRepository(db).add(
        SourceFile(
            dataset_id=d.id,
            filename="rec.wav",
            storage_path=f"uploads/{d.id}/rec.wav",
            duration_sec=5.0,
        )
    )
    JobRepository(db).add(Job(dataset_id=d.id, type="cutting", status="running"))
    db.commit()

    with pytest.raises(ConflictError):
        ProcessingService(db).start_cutting(
            d.id, ProcessRequest(common_labels={"distance_m": 10})
        )


# --- API 통합 테스트 (TestClient, 백그라운드 Job 실제 실행) ---


def test_process_runs_end_to_end(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=5.0, sample_rate=8000, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")
    dataset_id = upload["dataset_id"]

    r = client.post(
        f"/api/datasets/{dataset_id}/process",
        json={"common_labels": {"distance_m": 10}},
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] in ("queued", "running", "done")

    # TestClient는 BackgroundTasks를 응답 완료 전에 동기 실행한다.
    job_after = client.get(f"/api/jobs/{job['id']}").json()
    assert job_after["status"] == "done", job_after
    assert job_after["progress"] == 5  # 5초 / 1초 간격 = 5조각
    assert job_after["error_msg"] is None

    ds = client.get(f"/api/datasets/{dataset_id}").json()
    assert ds["status"] == "ready"

    jobs_list = client.get(f"/api/datasets/{dataset_id}/jobs").json()
    assert jobs_list["total"] == 1


def test_process_without_labels_allowed_unlabeled(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """common_labels 없이도 커팅은 진행된다 — 부분/후속 라벨링 허용.

    required 누락은 에러가 아니라 is_labeled=False로 반영된다(라벨링 진행률의 전제,
    PRD F6 / 05 §4). 라벨은 이후 PATCH /segments/{id}/labels 로 채운다.
    (단, naming_pattern이 라벨을 참조하지 않아야 한다 — 아래 fail-fast 테스트 참조.)
    """
    payload = _project_payload()
    payload["naming_pattern"] = "{date}_{seq:03d}"  # 라벨 비참조 패턴
    pid = client.post("/api/projects", json=payload).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")

    r = client.post(f"/api/datasets/{upload['dataset_id']}/process")
    assert r.status_code == 202, r.text
    segs = client.get(f"/api/datasets/{upload['dataset_id']}/segments").json()["items"]
    assert len(segs) > 0
    assert all(s["is_labeled"] is False for s in segs)


def test_process_fails_fast_when_naming_needs_missing_label(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """naming_pattern이 라벨({distance_m})을 참조하는데 common_labels에 없으면
    백그라운드 실패 대신 시작 전에 400으로 즉시 알려준다(fail-fast)."""
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")

    r = client.post(f"/api/datasets/{upload['dataset_id']}/process")
    assert r.status_code == 400
    assert "naming_pattern" in r.json()["detail"]
    assert "distance_m" in r.json()["detail"]


def test_process_rejects_bad_enum_label(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """제공된 값의 enum 위반은 여전히 400 (Job 시작 전 차단)."""
    payload = _project_payload()
    payload["label_schema"] = payload["label_schema"] + [
        {"key": "direction", "type": "enum", "options": ["N", "S"]}
    ]
    pid = client.post("/api/projects", json=payload).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")

    r = client.post(
        f"/api/datasets/{upload['dataset_id']}/process",
        json={"common_labels": {"direction": "X"}},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_process_missing_dataset_404(client: TestClient) -> None:
    r = client.post(
        "/api/datasets/9999/process", json={"common_labels": {"distance_m": 1}}
    )
    assert r.status_code == 404


def test_job_not_found_404(client: TestClient) -> None:
    r = client.get("/api/jobs/9999")
    assert r.status_code == 404


# --- A2: 고아 Job 복구 (docs/12) ---


def test_orphan_job_recovery_unblocks_dataset(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """크래시로 남은 running Job이 커팅을 영구 409로 막는 문제의 복구 (docs/12 A2)."""
    import app.background.worker as worker_module

    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=2.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]

    # 고아 상황 재현: running Job + dataset processing 상태를 직접 심는다
    db = worker_module.SessionLocal()
    from app.models.dataset import Dataset as DsModel

    db.add(Job(dataset_id=ds_id, type="cutting", status="running", params={}))
    db.get(DsModel, ds_id).status = "processing"
    db.commit()
    db.close()

    # 복구 전: 커팅이 409로 막힘 (고아가 잠그고 있음)
    r = client.post(
        f"/api/datasets/{ds_id}/process", json={"common_labels": {"distance_m": 1}}
    )
    assert r.status_code == 409

    # 서버 재기동에 해당하는 복구 실행
    recovered = worker_module.recover_orphan_jobs()
    assert recovered == 1

    # 복구 후: Job은 failed, dataset은 collecting, 커팅 가능
    db = worker_module.SessionLocal()
    orphan = db.query(Job).filter(Job.status == "failed").order_by(Job.id.desc()).first()
    assert "서버 재시작" in orphan.error_msg
    assert db.get(DsModel, ds_id).status == "collecting"
    db.close()
    r = client.post(
        f"/api/datasets/{ds_id}/process", json={"common_labels": {"distance_m": 1}}
    )
    assert r.status_code == 202, r.text
