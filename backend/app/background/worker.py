"""커팅 Job 실행 (MVP: FastAPI BackgroundTasks, V2: Celery로 승격 가능).

요청 스레드가 아니라 여기서 실제 무거운 작업을 한다. 요청 세션과 분리된
**자체 DB 세션**을 연다(요청이 끝나면 원래 세션은 닫히므로).

흐름: SourceFile마다 → registry에서 조회한 전략으로 자름 → 임시파일에 쓰고
Storage로 옮김(P3, 인터페이스 경유) → 메타 재추출 → Segment 기록 → 진행률 갱신.
전략별 분기문 없음(P1) — worker는 어떤 cutting_mode인지 몰라도 동작한다.
"""

import logging
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.audio.cutting import get_strategy
from app.audio.io import write_wav
from app.audio.metadata import extract_metadata
from app.audio.naming import render_filename
from app.core.database import SessionLocal
from app.hooks.events import on_dataset_exported, on_processing_done
from app.models.job import Job
from app.models.segment import Segment
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.job_repo import JobRepository
from app.repositories.segment_repo import SegmentRepository
from app.repositories.source_file_repo import SourceFileRepository
from app.services.dataset_service import build_metadata_csv
from app.services.label_validation import compute_is_labeled
from app.storage import get_storage
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def run_cutting_job(job_id: int) -> None:
    """BackgroundTasks가 호출하는 진입점. 항상 자체 세션을 열고 닫는다."""
    db = SessionLocal()
    storage = get_storage()
    job_repo = JobRepository(db)
    source_repo = SourceFileRepository(db)
    segment_repo = SegmentRepository(db)
    dataset_repo = DatasetRepository(db)

    job = job_repo.get(job_id)
    if job is None:
        db.close()
        return

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()

    try:
        _run(job, db, storage, source_repo, segment_repo)
        job.status = "done"
        job.total_items = job.progress
        job.finished_at = datetime.now(timezone.utc)
        dataset = dataset_repo.get(job.dataset_id)
        if dataset is not None:
            dataset.status = "ready"
        db.commit()
        on_processing_done.emit(dataset_id=job.dataset_id, job_id=job.id)
    except Exception as exc:  # noqa: BLE001 - Job 실패로 기록하고 흐름 유지
        logger.exception("cutting job %s 실패", job_id)
        db.rollback()
        job = job_repo.get(job_id)  # rollback 후 재조회
        if job is not None:
            job.status = "failed"
            job.error_msg = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def _run(
    job: Job,
    db: Session,
    storage: StorageBackend,
    source_repo: SourceFileRepository,
    segment_repo: SegmentRepository,
) -> None:
    params = job.params
    strategy = get_strategy(params["cutting_mode"])
    cutting_params = params["cutting_params"]
    naming_pattern = params["naming_pattern"]
    common_labels = params.get("common_labels") or {}
    label_schema = params.get("label_schema") or []
    source_file_ids: list[int] = params["source_file_ids"]

    # naming_pattern에서 쓸 수 있는 공통 값(공통 라벨 + 오늘 날짜).
    # seq는 이 Job 전체에 걸친 연속 번호(재현성 있는 순서).
    base_values = {**common_labels, "date": date.today().strftime("%Y%m%d")}
    is_labeled = compute_is_labeled(label_schema, common_labels)

    seq = 1
    with tempfile.TemporaryDirectory(prefix="cutting_job_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        for source_id in source_file_ids:
            source = source_repo.get(source_id)
            if source is None:
                continue
            local_source_path = storage.local_path(source.storage_path)

            for seg_audio in strategy.cut(local_source_path, cutting_params):
                values = {**base_values, "seq": seq}
                filename = render_filename(naming_pattern, values, extension="wav")

                tmp_file = tmp_path / f"tmp_{seq:06d}.wav"
                write_wav(tmp_file, seg_audio.samples, seg_audio.sample_rate)

                logical_path = f"segments/{job.dataset_id}/{filename}"
                storage.save_from_path(logical_path, tmp_file)
                tmp_file.unlink(missing_ok=True)

                meta = extract_metadata(storage.local_path(logical_path))
                segment_repo.add(
                    Segment(
                        dataset_id=job.dataset_id,
                        source_file_id=source.id,
                        filename=filename,
                        storage_path=logical_path,
                        duration_sec=meta.duration_sec,
                        sample_rate=meta.sample_rate,
                        channels=meta.channels,
                        bit_depth=meta.bit_depth,
                        file_size=meta.file_size,
                        format=meta.format,
                        source_start_sec=seg_audio.start_sec,
                        labels=common_labels,
                        is_labeled=is_labeled,
                    )
                )
                job.progress += 1
                db.commit()  # 진행률을 폴링에서 즉시 볼 수 있도록 매 세그먼트 커밋
                seq += 1


def run_export_job(job_id: int) -> None:
    """BackgroundTasks가 호출하는 CSV export 진입점(06_API.md §4.3). 커팅과 동일한 골격."""
    db = SessionLocal()
    storage = get_storage()
    job_repo = JobRepository(db)
    dataset_repo = DatasetRepository(db)
    segment_repo = SegmentRepository(db)

    job = job_repo.get(job_id)
    if job is None:
        db.close()
        return

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()

    try:
        result_path = _run_export(job, storage, dataset_repo, segment_repo)
        job.status = "done"
        job.result_path = result_path
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        on_dataset_exported.emit(
            dataset_id=job.dataset_id, job_id=job.id, result_path=result_path
        )
    except Exception as exc:  # noqa: BLE001 - Job 실패로 기록하고 흐름 유지
        logger.exception("export job %s 실패", job_id)
        db.rollback()
        job = job_repo.get(job_id)  # rollback 후 재조회
        if job is not None:
            job.status = "failed"
            job.error_msg = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def _run_export(
    job: Job,
    storage: StorageBackend,
    dataset_repo: DatasetRepository,
    segment_repo: SegmentRepository,
) -> str:
    dataset = dataset_repo.get(job.dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset {job.dataset_id}를 찾을 수 없습니다.")

    label_keys = [f["key"] for f in dataset.project.label_schema]
    segments = segment_repo.all_for_dataset(job.dataset_id)
    csv_text = build_metadata_csv(segments, label_keys)

    logical_path = f"exports/{job.dataset_id}/metadata.csv"
    with tempfile.TemporaryDirectory(prefix="export_job_") as tmp_dir:
        tmp_file = Path(tmp_dir) / "metadata.csv"
        tmp_file.write_text(csv_text, encoding="utf-8")
        storage.save_from_path(logical_path, tmp_file)

    job.total_items = len(segments)
    job.progress = len(segments)
    return logical_path
