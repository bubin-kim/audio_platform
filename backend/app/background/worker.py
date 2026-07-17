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
from app.audio.naming import render_filename, render_path
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.hooks.events import (
    on_dataset_exported,
    on_processing_done,
    on_processing_failed,
)
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


def recover_orphan_jobs() -> int:
    """서버 기동 시 고아 Job 정리 (docs/12 A2). 정리한 개수를 반환한다.

    Job 실행 중 서버가 죽으면 queued/running이 영원히 남아 has_running 가드가
    해당 dataset의 커팅을 영구히 409로 막는다. MVP는 단일 프로세스(BackgroundTasks)라
    기동 시점에 진행 중 Job이 존재할 수 없다 — 남아 있다면 전부 고아다.
    """
    db = SessionLocal()
    try:
        orphans = JobRepository(db).list_unfinished()
        for job in orphans:
            job.status = "failed"
            job.error_msg = "서버 재시작으로 중단됨 (고아 Job 자동 정리)"
            job.finished_at = datetime.now(timezone.utc)
            if job.type == "cutting" and job.dataset.status == "processing":
                job.dataset.status = "collecting"
        db.commit()
        if orphans:
            logger.warning("고아 Job %d개를 failed로 정리했습니다", len(orphans))
        return len(orphans)
    finally:
        db.close()


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
            # 실패 알림 훅 (V2-6, docs/14) — 현장에서 실패를 빨리 알아야 한다
            on_processing_failed.emit(
                dataset_id=job.dataset_id, job_id=job.id, error_msg=job.error_msg
            )
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
    replace_existing: bool = params.get("replace_existing", False)
    inherit: bool = params.get("inherit_labels", True)

    # naming_pattern에서 쓸 수 있는 공통 값(공통 라벨 + 오늘 날짜).
    base_values = {**common_labels, "date": date.today().strftime("%Y%m%d")}

    # 재처리(docs/10 §3): 스냅샷 → 기존 세그먼트 삭제를 커팅 전에 선행 패스로 —
    # 아래 seq 계산이 삭제 이후 개수를 보게 하기 위함.
    snapshots: dict[int, list[dict]] = {}
    if replace_existing:
        for source_id in source_file_ids:
            old_segments = segment_repo.list_by_source_file(source_id)
            if inherit:
                snapshots[source_id] = [
                    {
                        "start": s.source_start_sec,
                        "end": s.source_start_sec + s.duration_sec,
                        "labels": dict(s.labels or {}),
                    }
                    for s in old_segments
                ]
            for old in old_segments:
                storage.delete(old.storage_path)
                segment_repo.delete(old)
        db.commit()

    # seq는 Job 단위가 아니라 dataset 누적 (docs/12 A1) — Job마다 1부터 시작하면
    # 같은 날짜·같은 라벨의 별도 Job이 같은 파일명을 만들어 조용히 덮어쓴다.
    seq = segment_repo.count_by_dataset(job.dataset_id) + 1
    job.params = {**job.params, "seq_start": seq}  # 재현성 (JSON 변경 감지 위해 재할당)
    db.commit()

    # 품질 검사(docs/14): 원본별 조각 수 집계 → 기대치와 비교
    per_source_counts: dict[int, dict] = {}

    with tempfile.TemporaryDirectory(prefix="cutting_job_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        for source_id in source_file_ids:
            source = source_repo.get(source_id)
            if source is None:
                continue
            local_source_path = storage.local_path(source.storage_path)
            snapshot = snapshots.get(source_id, [])
            per_source_counts[source_id] = {"filename": source.filename, "actual": 0}

            for seg_audio in strategy.cut(local_source_path, cutting_params):
                values = {**base_values, "seq": seq}
                filename = render_filename(naming_pattern, values, extension="wav")

                tmp_file = tmp_path / f"tmp_{seq:06d}.wav"
                write_wav(tmp_file, seg_audio.samples, seg_audio.sample_rate)

                logical_path = f"segments/{job.dataset_id}/{filename}"
                # 조용한 덮어쓰기 금지 (docs/12 A1): 충돌은 명시적 실패로.
                if storage.exists(logical_path):
                    raise RuntimeError(
                        f"파일명 충돌: {logical_path} 가 이미 존재합니다. "
                        "naming_pattern에 구분 필드(예: {seq})가 부족하지 않은지 확인하세요."
                    )
                storage.save_from_path(logical_path, tmp_file)
                tmp_file.unlink(missing_ok=True)

                # 라벨 = 승계(겹침 매칭, 스키마 재검증) 위에 common_labels 덮어쓰기.
                inherited = _match_inherited_labels(
                    snapshot, seg_audio.start_sec, seg_audio.end_sec
                )
                inherited = _sanitize_inherited(label_schema, inherited)
                labels = {**inherited, **common_labels}

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
                        labels=labels,
                        is_labeled=compute_is_labeled(label_schema, labels),
                    )
                )
                job.progress += 1
                per_source_counts[source_id]["actual"] += 1
                db.commit()  # 진행률을 폴링에서 즉시 볼 수 있도록 매 세그먼트 커밋
                seq += 1

    # 품질 검사 결과를 Job에 기록 (기대치 미설정이면 생략 — docs/14)
    expected = params.get("expected_segments_per_source")
    if expected:
        sources_report = []
        for sid, info in per_source_counts.items():
            actual = info["actual"]
            status = (
                "ok" if actual == expected
                else "shortfall" if actual < expected
                else "excess"
            )
            sources_report.append(
                {
                    "source_file_id": sid,
                    "filename": info["filename"],
                    "expected": expected,
                    "actual": actual,
                    "status": status,
                }
            )
        job.params = {
            **job.params,
            "quality_check": {
                "expected": expected,
                "sources": sources_report,
                "ok": all(s["status"] == "ok" for s in sources_report),
            },
        }
        db.commit()


def _match_inherited_labels(
    snapshot: list[dict], start: float, end: float
) -> dict:
    """새 구간 [start, end)에 승계할 라벨을 스냅샷에서 고른다 (docs/10 §4).

    시간 겹침이 가장 큰 옛 조각의 라벨을 쓴다. 동률이면 새 조각의 중점을
    포함하는 쪽. 겹침이 전혀 없으면 빈 dict(옛 조각이 없던 구간).
    순수 함수 — 단독 테스트 가능.
    """
    best: dict = {}
    best_key: tuple[float, bool] = (0.0, False)
    mid = (start + end) / 2
    for item in snapshot:
        overlap = min(end, item["end"]) - max(start, item["start"])
        if overlap <= 0:
            continue
        key = (overlap, item["start"] <= mid < item["end"])
        if key > best_key:
            best, best_key = item["labels"], key
    return dict(best)


def _sanitize_inherited(label_schema: list[dict], labels: dict) -> dict:
    """승계 라벨을 현재 스키마로 재검증 — 위반 키만 제외하고 로그 (docs/10 §4).

    재처리 사이에 label_schema가 바뀌었을 수 있으므로 키 단위로 걸러낸다.
    """
    from app.core.exceptions import ValidationError
    from app.services.label_validation import validate_labels

    clean: dict = {}
    for key, value in labels.items():
        try:
            validate_labels(label_schema, {key: value})
            clean[key] = value
        except ValidationError:
            logger.warning("승계 라벨 '%s'=%r 가 현재 스키마와 맞지 않아 제외", key, value)
    return clean


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

    project = dataset.project
    label_keys = [f["key"] for f in project.label_schema]
    segments = segment_repo.all_for_dataset(job.dataset_id)
    csv_text = build_metadata_csv(
        segments,
        label_keys,
        project_name=project.name,
        dataset_name=dataset.name,
        dataset_version=dataset.version,
    )

    # 경로는 설정 패턴으로 (docs/11 §2). 값 채우기는 DB를 아는 여기(worker)서 —
    # Storage는 여전히 프로젝트를 모른다(P2). 패턴은 Job.params에 기록된 것을 쓴다(재현성).
    pattern = job.params.get(
        "export_path_pattern", get_settings().export_path_pattern
    )
    logical_path = render_path(
        pattern,
        {
            "project": project.name,
            "dataset": dataset.name,
            "version": dataset.version,
            "date": date.today().strftime("%Y%m%d"),
            "project_id": project.id,
            "dataset_id": dataset.id,
        },
    )
    with tempfile.TemporaryDirectory(prefix="export_job_") as tmp_dir:
        tmp_file = Path(tmp_dir) / "export.csv"
        tmp_file.write_text(csv_text, encoding="utf-8")
        storage.save_from_path(logical_path, tmp_file)

    job.total_items = len(segments)
    job.progress = len(segments)
    return logical_path
