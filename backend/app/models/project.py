"""Project 테이블 — 도메인 설정의 집 (05 §3.1).

도메인의 차이(커팅 방식·파일명 규칙·라벨)는 전부 이 레코드의 설정값에 담긴다(P1).
코드는 이 값들로 분기하지 않고 전략 registry를 조회할 뿐이다.
"""

from typing import Any

from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 분류/필터용 태그일 뿐. 코드가 이 값으로 분기하지 않는다(P1).
    domain: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 커팅 전략 registry 키 ("fixed_interval" 등) + 전략별 파라미터.
    cutting_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    cutting_params: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # 파일명 생성 규칙. 예: "{date}_{model}_{distance}_{seq:03d}"
    naming_pattern: Mapped[str] = mapped_column(String(300), nullable=False)

    # 이 프로젝트가 요구하는 라벨 정의(2 §2). 리스트[{key,type,required,options?}].
    label_schema: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )

    # 대시보드 "업로드 진행률" 분모(목표 총 녹음시간, 초). 없으면 진행률 미표시.
    target_duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 원본 1개당 기대 조각 수 (품질 검사, docs/14). 없으면 검사 안 함.
    expected_segments_per_source: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # 전체 수집 목표(세그먼트 개수, docs/15). 대시보드 "수집 진행률" 게이지 분모.
    target_segment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    datasets: Mapped[list["Dataset"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    upload_histories: Mapped[list["UploadHistory"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
