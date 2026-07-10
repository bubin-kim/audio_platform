"""Project 서비스 — 업무 흐름 조립 (얇은 API 계층 위임 대상, 02 §2).

DB 접근은 Repository, 커팅 전략 유효성은 audio registry로 위임한다.
`if domain==...` 분기문은 없다(P1). cutting_mode는 registry에 있는지만 확인한다.
"""

from sqlalchemy.orm import Session

from app.audio.cutting import available_strategies
from app.core.exceptions import NotFoundError, ValidationError
from app.models.project import Project
from app.repositories.project_repo import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProjectRepository(db)

    def create(self, data: ProjectCreate) -> Project:
        self._validate_cutting_mode(data.cutting_mode)
        project = Project(
            name=data.name,
            domain=data.domain,
            cutting_mode=data.cutting_mode,
            cutting_params=data.cutting_params,
            naming_pattern=data.naming_pattern,
            label_schema=[f.model_dump() for f in data.label_schema],
            target_duration_sec=data.target_duration_sec,
        )
        self.repo.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get(self, project_id: int) -> Project:
        project = self.repo.get(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id}를 찾을 수 없습니다.")
        return project

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Project], int]:
        return self.repo.list(limit=limit, offset=offset), self.repo.count()

    def update(self, project_id: int, data: ProjectUpdate) -> Project:
        project = self.get(project_id)
        fields = data.model_dump(exclude_unset=True)
        if "cutting_mode" in fields and fields["cutting_mode"] is not None:
            self._validate_cutting_mode(fields["cutting_mode"])
        if "label_schema" in fields and fields["label_schema"] is not None:
            fields["label_schema"] = [f.model_dump() for f in data.label_schema]
        for key, value in fields.items():
            setattr(project, key, value)
        self.db.commit()
        self.db.refresh(project)
        return project

    def _validate_cutting_mode(self, mode: str) -> None:
        if mode not in available_strategies():
            raise ValidationError(
                f"알 수 없는 cutting_mode='{mode}'. "
                f"사용 가능: {available_strategies()}"
            )
