"""ORM 모델 패키지.

여기서 모든 모델을 임포트해 Base.metadata에 등록되게 한다.
alembic env.py 의 `import app.models` 가 이 파일을 통해 전 테이블을 잡는다.
"""

from app.models.dataset import Dataset
from app.models.history import UploadHistory
from app.models.job import Job
from app.models.project import Project
from app.models.segment import Segment
from app.models.source_file import SourceFile

__all__ = [
    "Project",
    "Dataset",
    "Segment",
    "SourceFile",
    "Job",
    "UploadHistory",
]
