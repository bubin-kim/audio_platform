"""ntfy 푸시 알림 구독자 (V2-6 — docs/14).

커팅 완료/실패를 연구원 휴대폰으로 푸시한다. 품질 검사(기대 조각 수) 결과가
이상이면 경고 우선순위로 보낸다. Notion 구독자와 동일한 P4 플러그인:
NTFY_TOPIC 미설정이면 register가 no-op, 발송 실패는 로그만(본 흐름 보호).
"""

import logging
import threading
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal  # 모듈 심볼 (테스트 몽키패치용)
from app.hooks.events import on_processing_done, on_processing_failed
from app.repositories.dataset_repo import DatasetRepository
from app.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)


# --- [1] 발송 클라이언트 -------------------------------------------------------


class NtfyClient:
    """ntfy REST 발송 최소 래퍼. transport는 테스트 MockTransport 주입용."""

    def __init__(
        self,
        *,
        server: str,
        topic: str,
        timeout_sec: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = f"{server.rstrip('/')}/{topic}"
        self._timeout = timeout_sec
        self._transport = transport

    def send(self, *, title: str, message: str, priority: str = "default",
             tags: str = "") -> None:
        """푸시 발송. HTTP 헤더는 latin-1 제약이 있으므로(재생 500 사고의 교훈)
        한글 제목은 헤더 대신 본문 첫 줄로 보낸다 — 본문은 UTF-8 자유."""
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport

        headers: dict[str, str] = {"Priority": priority}
        if tags:
            headers["Tags"] = tags
        if title.isascii():
            headers["Title"] = title
            body = message
        else:
            body = f"[{title}]\n{message}"

        with httpx.Client(**kwargs) as client:
            res = client.post(self._url, content=body.encode("utf-8"), headers=headers)
            res.raise_for_status()


def _make_client() -> NtfyClient:
    """설정으로 클라이언트 생성. 테스트에서 이 함수를 몽키패치한다."""
    settings = get_settings()
    return NtfyClient(
        server=settings.ntfy_server,
        topic=settings.ntfy_topic,
        timeout_sec=settings.ntfy_timeout_sec,
    )


# --- [2] 비차단 실행 (notion과 동일 패턴) --------------------------------------


def _spawn(target: Callable[..., None], **kwargs: Any) -> None:
    threading.Thread(target=target, kwargs=kwargs, daemon=True).start()


# --- [3] 구독자 ---------------------------------------------------------------


def _handle_processing_done(dataset_id: int, job_id: int) -> None:
    _spawn(_notify_done, dataset_id=dataset_id, job_id=job_id)


def _notify_done(dataset_id: int, job_id: int) -> None:
    """커팅 완료 → 정상이면 기본, 품질 이상이면 경고 우선순위 푸시 (docs/14)."""
    db = SessionLocal()
    try:
        dataset = DatasetRepository(db).get(dataset_id)
        job = JobRepository(db).get(job_id)
        if dataset is None or job is None:
            return
        project_name = dataset.project.name
        qc = (job.params or {}).get("quality_check")

        if qc and not qc.get("ok", True):
            bad = [s for s in qc["sources"] if s["status"] != "ok"]
            lines = [
                f"{s['actual']}/{s['expected']}조각 "
                f"({'부족' if s['status'] == 'shortfall' else '초과'}) — {s['filename']}"
                for s in bad
            ]
            _make_client().send(
                title="조각 수 이상 — 재녹음 검토",
                message=f"⚠️ {project_name} / {dataset.name}\n"
                + "\n".join(lines)
                + f"\n(Job #{job.id})",
                priority="high",
                tags="warning",
            )
        else:
            _make_client().send(
                title="커팅 완료",
                message=(
                    f"✅ {project_name} / {dataset.name} — "
                    f"{job.total_items}조각 (Job #{job.id})"
                ),
                tags="white_check_mark",
            )
        logger.info("ntfy: 커팅 완료 알림 발송 (job=%s)", job_id)
    except Exception:  # noqa: BLE001 - 스레드 안 → 자체 처리 (본 흐름 보호)
        logger.exception("ntfy: 완료 알림 발송 실패 (job=%s)", job_id)
    finally:
        db.close()


def _handle_processing_failed(dataset_id: int, job_id: int, error_msg: str) -> None:
    _spawn(_notify_failed, dataset_id=dataset_id, job_id=job_id, error_msg=error_msg)


def _notify_failed(dataset_id: int, job_id: int, error_msg: str) -> None:
    db = SessionLocal()
    try:
        dataset = DatasetRepository(db).get(dataset_id)
        name = f"{dataset.project.name} / {dataset.name}" if dataset else f"dataset {dataset_id}"
        _make_client().send(
            title="커팅 실패",
            message=f"❌ {name} — Job #{job_id}: {error_msg[:120]}",
            priority="high",
            tags="x",
        )
        logger.info("ntfy: 커팅 실패 알림 발송 (job=%s)", job_id)
    except Exception:  # noqa: BLE001
        logger.exception("ntfy: 실패 알림 발송 실패 (job=%s)", job_id)
    finally:
        db.close()


# --- [4] 등록 -----------------------------------------------------------------


def register_ntfy_subscribers(settings: Settings | None = None) -> bool:
    """NTFY_TOPIC 설정 시에만 구독 등록. 미설정이면 no-op (P4)."""
    settings = settings or get_settings()
    if not settings.ntfy_enabled:
        logger.info("ntfy: 미설정 — 구독자 등록 생략 (플랫폼은 정상 동작)")
        return False
    on_processing_done.subscribe(_handle_processing_done)
    on_processing_failed.subscribe(_handle_processing_failed)
    logger.info("ntfy: 구독자 등록 완료 (processing_done, processing_failed)")
    return True
