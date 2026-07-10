"""Repository CRUD·쿼리 테스트 (인메모리 DB)."""

from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.segment import Segment
from app.repositories import (
    DatasetRepository,
    JobRepository,
    ProjectRepository,
    SegmentRepository,
    SourceFileRepository,
    UploadHistoryRepository,
)
from app.models.dataset import Dataset
from app.models.history import UploadHistory
from app.models.project import Project
from app.models.source_file import SourceFile


def _make_project(db: Session) -> Project:
    repo = ProjectRepository(db)
    p = Project(
        name="차량음",
        domain="vehicle",
        cutting_mode="fixed_interval",
        cutting_params={"interval_sec": 3.0},
        naming_pattern="{date}_{seq:03d}",
        label_schema=[{"key": "distance_m", "type": "number", "required": True}],
        target_duration_sec=3600.0,
    )
    return repo.add(p)


def test_project_crud(db: Session) -> None:
    repo = ProjectRepository(db)
    p = _make_project(db)
    db.commit()
    assert p.id is not None
    got = repo.get(p.id)
    assert got is not None and got.cutting_params["interval_sec"] == 3.0
    assert repo.count() == 1


def test_dataset_by_project_and_first(db: Session) -> None:
    p = _make_project(db)
    d_repo = DatasetRepository(db)
    d1 = d_repo.add(Dataset(project_id=p.id, name="v1", version="v1"))
    d_repo.add(Dataset(project_id=p.id, name="v2", version="v2"))
    db.commit()
    assert len(d_repo.list_by_project(p.id)) == 2
    # first_for_project = 가장 오래된 것(자동선택 대상)
    assert d_repo.first_for_project(p.id).id == d1.id


def test_segment_bulk_and_count(db: Session) -> None:
    p = _make_project(db)
    d = DatasetRepository(db).add(Dataset(project_id=p.id, name="v1"))
    db.flush()
    s_repo = SegmentRepository(db)
    segs = [
        Segment(
            dataset_id=d.id,
            filename=f"seg_{i:03d}.wav",
            storage_path=f"segments/{d.id}/seg_{i:03d}.wav",
            duration_sec=3.0,
            sample_rate=44100,
            channels=1,
            bit_depth=16,
            file_size=1000,
            format="wav",
            labels={"distance_m": i},
        )
        for i in range(5)
    ]
    s_repo.add_many(segs)
    db.commit()
    assert s_repo.count_by_dataset(d.id) == 5
    assert len(s_repo.all_for_dataset(d.id)) == 5
    # JSON 라벨 왕복
    assert s_repo.all_for_dataset(d.id)[0].labels == {"distance_m": 0}


def test_job_has_running_guard(db: Session) -> None:
    p = _make_project(db)
    d = DatasetRepository(db).add(Dataset(project_id=p.id, name="v1"))
    db.flush()
    j_repo = JobRepository(db)
    assert not j_repo.has_running(d.id, "cutting")
    j_repo.add(Job(dataset_id=d.id, type="cutting", status="running"))
    db.commit()
    assert j_repo.has_running(d.id, "cutting")
    assert not j_repo.has_running(d.id, "export")


def test_source_file_and_history(db: Session) -> None:
    p = _make_project(db)
    d = DatasetRepository(db).add(Dataset(project_id=p.id, name="v1"))
    db.flush()
    sf_repo = SourceFileRepository(db)
    sf_repo.add(
        SourceFile(
            dataset_id=d.id,
            filename="rec.wav",
            storage_path="uploads/1/rec.wav",
            duration_sec=14400.0,
        )
    )
    h_repo = UploadHistoryRepository(db)
    h_repo.add(UploadHistory(project_id=p.id, filename="rec.wav", file_size=999))
    db.commit()
    assert len(sf_repo.list_by_dataset(d.id)) == 1
    assert h_repo.recent(limit=5)[0].filename == "rec.wav"
