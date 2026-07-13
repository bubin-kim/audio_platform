"""Upload 서비스 — 업로드 오케스트레이션 (02 §3 흐름 1~2).

흐름: 파일 저장(Storage) → 메타 추출(Audio) → SourceFile·UploadHistory 기록(Repo)
      → on_upload_complete 훅. 각 처리는 하위 계층에 위임하고 여기선 조립만 한다.
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.audio.metadata import extract_metadata
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.hooks.events import on_upload_complete
from app.models.source_file import SourceFile
from app.repositories.history_repo import UploadHistoryRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.source_file_repo import SourceFileRepository
from app.models.history import UploadHistory
from app.services.dataset_service import DatasetService
from app.storage.base import StorageBackend

# 지원 포맷 (wav 우선, 나머지는 ffmpeg 경유 — 06_API.md §5).
ALLOWED_FORMATS = {"wav", "mp3", "flac", "m4a"}


@dataclass
class UploadedFile:
    """라우터가 읽어 넘기는 업로드 파일 한 개 (프레임워크 독립)."""

    filename: str
    data: bytes


class UploadService:
    def __init__(self, db: Session, storage: StorageBackend) -> None:
        self.db = db
        self.storage = storage
        self.project_repo = ProjectRepository(db)
        self.source_repo = SourceFileRepository(db)
        self.history_repo = UploadHistoryRepository(db)
        self.dataset_service = DatasetService(db)

    def register_uploads(
        self,
        project_id: int,
        files: list[UploadedFile],
        dataset_id: int | None = None,
    ) -> tuple[int, bool, list[SourceFile]]:
        """원본들을 저장·등록한다. (dataset_id, created_dataset, sources) 반환."""
        if self.project_repo.get(project_id) is None:
            raise NotFoundError(f"Project {project_id}를 찾을 수 없습니다.")
        if not files:
            raise ValidationError("업로드할 파일이 없습니다.")

        dataset, created = self._resolve_dataset(project_id, dataset_id)

        sources: list[SourceFile] = []
        for uf in files:
            sources.append(self._register_one(project_id, dataset.id, uf))

        self.db.commit()
        for s in sources:
            self.db.refresh(s)

        # 훅 발화 (MVP 구독자 없음). 본 흐름을 막지 않는다.
        on_upload_complete.emit(
            project_id=project_id,
            dataset_id=dataset.id,
            source_ids=[s.id for s in sources],
        )
        return dataset.id, created, sources

    def _resolve_dataset(
        self, project_id: int, dataset_id: int | None
    ) -> tuple[object, bool]:
        if dataset_id is not None:
            dataset = self.dataset_service.get(dataset_id)
            if dataset.project_id != project_id:
                raise ValidationError(
                    f"Dataset {dataset_id}는 Project {project_id}에 속하지 않습니다."
                )
            return dataset, False
        # 미지정 → 기본 Dataset 선택/자동생성 (결정 4).
        return self.dataset_service.get_or_create_default(project_id)

    def _register_one(
        self, project_id: int, dataset_id: int, uf: UploadedFile
    ) -> SourceFile:
        fmt = Path(uf.filename).suffix.lstrip(".").lower()
        if fmt not in ALLOWED_FORMATS:
            raise ValidationError(
                f"지원하지 않는 포맷 '{fmt}'. 지원: {sorted(ALLOWED_FORMATS)}"
            )
        safe_name = Path(uf.filename).name
        # 중복 업로드 차단 (docs/12 B2): 같은 이름 재업로드는 파일을 덮어쓰고
        # row만 중복 생성되던 실사고 재발 방지. 저장 전에 검사해 파일 훼손도 막는다.
        duplicates = [
            sf
            for sf in self.source_repo.list_by_dataset(dataset_id)
            if sf.filename == safe_name
        ]
        if duplicates:
            raise ConflictError(
                f"'{safe_name}'은 이미 이 Dataset에 업로드되어 있습니다"
                f"(SourceFile id={duplicates[0].id}). 재업로드하려면 기존 원본을 "
                "삭제(DELETE /source-files/{id})하거나 파일명을 바꾸세요."
            )
        logical_path = f"uploads/{dataset_id}/{safe_name}"
        self.storage.save(logical_path, uf.data)

        # 메타 추출은 실제 파일 경로가 필요 → Storage가 해석해준다.
        meta = extract_metadata(self.storage.local_path(logical_path))

        source = SourceFile(
            dataset_id=dataset_id,
            filename=safe_name,
            storage_path=logical_path,
            duration_sec=meta.duration_sec,
            sample_rate=meta.sample_rate,
            channels=meta.channels,
            bit_depth=meta.bit_depth,
            file_size=meta.file_size,
            format=meta.format,
        )
        self.source_repo.add(source)
        self.history_repo.add(
            UploadHistory(
                project_id=project_id,
                filename=safe_name,
                file_size=meta.file_size,
            )
        )
        return source
