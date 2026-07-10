"""Segment 서비스 — 개별 라벨 수정 (06_API.md §8).

기본 라벨링은 커팅 시 common_labels로 일괄 처리된다. 여기는 예외 보정용:
특정 세그먼트만 값이 다를 때 기존 labels 위에 부분 덮어쓰기(merge)한다.
검증 규칙은 common_labels와 동일한 label_validation을 재사용한다(한 곳의 규칙).
"""

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.segment import Segment
from app.repositories.segment_repo import SegmentRepository
from app.services.label_validation import compute_is_labeled, validate_labels


class SegmentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SegmentRepository(db)

    def get(self, segment_id: int) -> Segment:
        segment = self.repo.get(segment_id)
        if segment is None:
            raise NotFoundError(f"Segment {segment_id}를 찾을 수 없습니다.")
        return segment

    def update_labels(self, segment_id: int, labels: dict[str, Any]) -> Segment:
        """기존 labels 위에 부분 덮어쓰기 → schema 검증 → is_labeled 재계산."""
        segment = self.get(segment_id)
        label_schema = segment.dataset.project.label_schema

        merged = {**(segment.labels or {}), **labels}
        validate_labels(label_schema, merged)  # 위반 시 ValidationError(400)

        segment.labels = merged
        segment.is_labeled = compute_is_labeled(label_schema, merged)
        self.db.commit()
        self.db.refresh(segment)
        return segment
