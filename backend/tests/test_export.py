"""Dataset CSV export 테스트 (M7, 06_API.md §4.3).

- DatasetService.start_export 단위 테스트: 404·409 규칙.
- build_metadata_csv 단위 테스트: 자동 메타데이터 + 동적 라벨 컬럼.
- API 통합 테스트: 업로드 → 커팅 → export → CSV 내용 검증.
"""

import csv
import io
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.dataset import Dataset
from app.models.job import Job
from app.models.project import Project
from app.models.segment import Segment
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.services.dataset_service import DatasetService, build_metadata_csv
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


# --- build_metadata_csv 단위 테스트 (순수 함수, DB 불필요) ---


def test_build_metadata_csv_includes_dynamic_label_columns() -> None:
    seg = Segment(
        id=1,
        dataset_id=1,
        filename="a.wav",
        storage_path="segments/1/a.wav",
        duration_sec=3.0,
        sample_rate=44100,
        channels=1,
        bit_depth=16,
        file_size=1000,
        format="wav",
        source_start_sec=0.0,
        labels={"distance_m": 10, "direction": "N"},
        is_labeled=True,
    )
    csv_text = build_metadata_csv([seg], label_keys=["distance_m", "direction"])
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 1
    assert rows[0]["filename"] == "a.wav"
    assert rows[0]["distance_m"] == "10"
    assert rows[0]["direction"] == "N"


def test_build_metadata_csv_missing_label_is_blank() -> None:
    seg = Segment(
        id=1,
        dataset_id=1,
        filename="a.wav",
        storage_path="segments/1/a.wav",
        duration_sec=3.0,
        sample_rate=44100,
        channels=1,
        bit_depth=16,
        file_size=1000,
        format="wav",
        source_start_sec=0.0,
        labels={},
        is_labeled=False,
    )
    csv_text = build_metadata_csv([seg], label_keys=["distance_m"])
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows[0]["distance_m"] == ""


# --- DatasetService.start_export 단위 테스트 (인메모리 DB) ---


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


def test_start_export_missing_dataset_404(db: Session) -> None:
    with pytest.raises(NotFoundError):
        DatasetService(db).start_export(999)


def test_start_export_conflict_when_already_running(db: Session) -> None:
    p = _make_project(db)
    d = DatasetRepository(db).add(Dataset(project_id=p.id, name="v1"))
    db.flush()
    JobRepository(db).add(Job(dataset_id=d.id, type="export", status="running"))
    db.commit()

    with pytest.raises(ConflictError):
        DatasetService(db).start_export(d.id)


# --- API 통합 테스트 (TestClient, 백그라운드 Job 실제 실행) ---


def test_export_runs_end_to_end(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=3.0, sample_rate=8000, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")
    dataset_id = upload["dataset_id"]

    proc = client.post(
        f"/api/datasets/{dataset_id}/process",
        json={"common_labels": {"distance_m": 10}},
    )
    assert proc.status_code == 202, proc.text

    r = client.get(f"/api/datasets/{dataset_id}/export")
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["type"] == "export"

    job_after = client.get(f"/api/jobs/{job['id']}").json()
    assert job_after["status"] == "done", job_after
    assert job_after["progress"] == 3  # 3초 / 1초 간격 = 3조각
    assert job_after["result_path"] == f"exports/{dataset_id}/metadata.csv"

    csv_bytes = client._storage.read(job_after["result_path"])
    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))
    assert len(rows) == 3
    assert rows[0]["distance_m"] == "10"
    assert rows[0]["is_labeled"] == "True"


def test_export_missing_dataset_404(client: TestClient) -> None:
    r = client.get("/api/datasets/9999/export")
    assert r.status_code == 404


def test_download_export_returns_csv_bytes(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=2.0, sample_rate=8000, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")
    dataset_id = upload["dataset_id"]

    client.post(
        f"/api/datasets/{dataset_id}/process",
        json={"common_labels": {"distance_m": 10}},
    )
    client.get(f"/api/datasets/{dataset_id}/export")

    r = client.get(f"/api/datasets/{dataset_id}/export/download")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    # 파일명 = <프로젝트명>_metadata.csv. 한글은 RFC 5987 filename*로 실린다.
    disposition = r.headers["content-disposition"]
    assert "attachment" in disposition
    assert quote("차량음_metadata.csv") in disposition
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 2


def test_download_filename_ascii_project(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    payload = {**_project_payload(), "name": "Heart Sounds v2"}
    pid = client.post("/api/projects", json=payload).json()["id"]
    wav = make_wav(duration_sec=1.0, name="rec.wav")
    dataset_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    client.post(
        f"/api/datasets/{dataset_id}/process",
        json={"common_labels": {"distance_m": 10}},
    )
    client.get(f"/api/datasets/{dataset_id}/export")

    r = client.get(f"/api/datasets/{dataset_id}/export/download")
    assert r.status_code == 200
    # 공백은 _로 치환되고 ASCII 이름은 filename=에도 그대로 담긴다.
    assert 'filename="Heart_Sounds_v2_metadata.csv"' in r.headers["content-disposition"]


def test_download_export_without_prior_export_404(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=1.0, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")

    r = client.get(f"/api/datasets/{upload['dataset_id']}/export/download")
    assert r.status_code == 404


def test_list_segments_after_cutting(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=3.0, sample_rate=8000, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")
    dataset_id = upload["dataset_id"]

    client.post(
        f"/api/datasets/{dataset_id}/process",
        json={"common_labels": {"distance_m": 10}},
    )

    r = client.get(f"/api/datasets/{dataset_id}/segments")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["items"][0]["labels"]["distance_m"] == 10
    assert body["items"][0]["is_labeled"] is True


def test_list_segments_missing_dataset_404(client: TestClient) -> None:
    r = client.get("/api/datasets/9999/segments")
    assert r.status_code == 404
