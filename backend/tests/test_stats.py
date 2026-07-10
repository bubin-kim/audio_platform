"""Stats(대시보드) 서비스·API 테스트 (M8, 06_API.md §9).

- StatsService 단위 테스트: 집계 수식(총합/평균/분포/진행률)을 인메모리 DB로 직접 검증.
- API 통합 테스트: 업로드→커팅으로 만든 실제 Segment가 /api/stats에 반영되는지 확인.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.dataset import Dataset
from app.models.project import Project
from app.models.segment import Segment
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.segment_repo import SegmentRepository
from app.services.stats_service import StatsService
from tests.conftest import upload_file


def _seg(dataset_id: int, *, duration: float, sr: int, size: int, labeled: bool) -> Segment:
    return Segment(
        dataset_id=dataset_id,
        filename=f"seg_{duration}.wav",
        storage_path=f"segments/{dataset_id}/seg_{duration}.wav",
        duration_sec=duration,
        sample_rate=sr,
        channels=1,
        bit_depth=16,
        file_size=size,
        format="wav",
        labels={},
        is_labeled=labeled,
    )


@pytest.fixture
def two_project_data(db: Session) -> dict:
    """Project A(target 있음, 3세그먼트) + Project B(target 없음, 2세그먼트)."""
    proj_repo = ProjectRepository(db)
    ds_repo = DatasetRepository(db)
    seg_repo = SegmentRepository(db)

    a = proj_repo.add(
        Project(
            name="차량음",
            cutting_mode="fixed_interval",
            cutting_params={"interval_sec": 1.0},
            naming_pattern="{date}_{seq:03d}",
            label_schema=[{"key": "distance_m", "type": "number", "required": True}],
            target_duration_sec=3600.0,
        )
    )
    b = proj_repo.add(
        Project(
            name="심음",
            cutting_mode="fixed_interval",
            cutting_params={"interval_sec": 1.0},
            naming_pattern="{date}_{seq:03d}",
            label_schema=[],
            target_duration_sec=None,
        )
    )
    db.flush()
    ds_a = ds_repo.add(Dataset(project_id=a.id, name="v1"))
    ds_b = ds_repo.add(Dataset(project_id=b.id, name="v1"))
    db.flush()

    seg_repo.add_many(
        [
            _seg(ds_a.id, duration=1.0, sr=44100, size=100, labeled=True),
            _seg(ds_a.id, duration=2.0, sr=44100, size=200, labeled=True),
            _seg(ds_a.id, duration=3.0, sr=44100, size=300, labeled=False),
            _seg(ds_b.id, duration=5.0, sr=48000, size=500, labeled=False),
            _seg(ds_b.id, duration=5.0, sr=48000, size=500, labeled=False),
        ]
    )
    db.commit()
    return {"project_a": a, "project_b": b}


# --- StatsService 단위 테스트 ---


def test_global_stats_aggregate_across_projects(
    db: Session, two_project_data: dict
) -> None:
    stats = StatsService(db).get_stats()

    assert stats.total_segments == 5
    assert stats.total_duration_sec == pytest.approx(16.0)
    assert stats.total_size_bytes == 1600
    assert stats.avg_duration_sec == pytest.approx(3.2)
    assert stats.sample_rate_distribution == {"44100": 3, "48000": 2}
    assert stats.format_distribution == {"wav": 5}
    assert stats.labeling_progress.labeled == 2
    assert stats.labeling_progress.total == 5
    assert stats.labeling_progress.ratio == pytest.approx(0.4)

    # target_sec: target이 설정된 프로젝트(A)만 합산.
    assert stats.upload_progress.target_sec == pytest.approx(3600.0)
    assert stats.upload_progress.ratio == pytest.approx(16.0 / 3600.0)

    assert stats.per_project is not None
    by_name = {p.name: p for p in stats.per_project}
    assert by_name["차량음"].segment_count == 3
    assert by_name["차량음"].duration_sec == pytest.approx(6.0)
    assert by_name["심음"].segment_count == 2
    assert by_name["심음"].duration_sec == pytest.approx(10.0)


def test_project_scoped_stats_limits_to_that_project(
    db: Session, two_project_data: dict
) -> None:
    a = two_project_data["project_a"]
    stats = StatsService(db).get_stats(project_id=a.id)

    assert stats.total_segments == 3
    assert stats.total_duration_sec == pytest.approx(6.0)
    assert stats.sample_rate_distribution == {"44100": 3}
    assert stats.upload_progress.target_sec == pytest.approx(3600.0)
    assert stats.per_project is None  # 프로젝트 범위 조회는 per_project를 채우지 않는다.


def test_project_scoped_stats_null_target_gives_null_ratio(
    db: Session, two_project_data: dict
) -> None:
    b = two_project_data["project_b"]
    stats = StatsService(db).get_stats(project_id=b.id)

    assert stats.upload_progress.target_sec is None
    assert stats.upload_progress.ratio is None


def test_stats_missing_project_404(db: Session) -> None:
    with pytest.raises(NotFoundError):
        StatsService(db).get_stats(project_id=999)


def test_stats_empty_dataset_has_null_ratios_not_crash(db: Session) -> None:
    stats = StatsService(db).get_stats()
    assert stats.total_segments == 0
    assert stats.total_duration_sec == 0.0
    assert stats.avg_duration_sec == 0.0
    assert stats.sample_rate_distribution == {}
    assert stats.labeling_progress.ratio is None
    assert stats.upload_progress.ratio is None
    assert stats.per_project == []


# --- API 통합 테스트 (TestClient, 업로드→커팅→stats) ---


def _project_payload() -> dict:
    return {
        "name": "차량음",
        "domain": "vehicle",
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [{"key": "distance_m", "type": "number", "required": True}],
        "target_duration_sec": 3600,
    }


def test_stats_api_reflects_real_pipeline(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=4.0, sample_rate=8000, name="rec.wav")
    upload = upload_file(client, pid, wav, "rec.wav")

    proc = client.post(
        f"/api/datasets/{upload['dataset_id']}/process",
        json={"common_labels": {"distance_m": 10}},
    )
    assert proc.status_code == 202, proc.text

    r = client.get("/api/stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_segments"] == 4  # 4초 / 1초 간격
    assert body["labeling_progress"]["labeled"] == 4
    assert body["per_project"][0]["segment_count"] == 4

    r2 = client.get(f"/api/stats?project_id={pid}")
    assert r2.status_code == 200
    assert r2.json()["per_project"] is None


def test_stats_api_missing_project_404(client: TestClient) -> None:
    r = client.get("/api/stats?project_id=9999")
    assert r.status_code == 404
