"""세그먼트 개별 라벨 PATCH 테스트 (06_API.md §8 — 예외 보정용).

커팅으로 만든 세그먼트의 labels를 부분 덮어쓰기하고, schema 검증·is_labeled
재계산이 동작하는지 확인한다.
"""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import upload_file


def _project_payload() -> dict:
    return {
        "name": "차량음",
        "domain": "vehicle",
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [
            {"key": "distance_m", "type": "number", "required": True},
            {"key": "direction", "type": "enum", "options": ["N", "S"]},
        ],
    }


def _make_segments(
    client: TestClient, make_wav: Callable[..., Path], common_labels: dict | None = None
) -> list[dict]:
    """프로젝트 생성→업로드→커팅까지 돌리고 세그먼트 목록을 돌려준다."""
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=3.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    body = {"common_labels": common_labels} if common_labels is not None else {}
    r = client.post(f"/api/datasets/{ds_id}/process", json=body)
    assert r.status_code == 202, r.text
    # TestClient에서 BackgroundTasks는 응답 후 동기 실행 → 이미 완료 상태
    segs = client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    assert len(segs) == 3
    return segs


def test_patch_merges_on_common_labels(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    segs = _make_segments(client, make_wav, {"distance_m": 10, "direction": "N"})
    seg = segs[0]
    # 한 세그먼트만 direction 예외 보정 (distance_m은 유지돼야 함 = merge)
    r = client.patch(
        f"/api/segments/{seg['id']}/labels", json={"labels": {"direction": "S"}}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["labels"] == {"distance_m": 10, "direction": "S"}
    assert body["is_labeled"] is True


def test_patch_fills_required_recomputes_is_labeled(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    # common_labels 없이 커팅 → required 미충족 → is_labeled=False
    segs = _make_segments(client, make_wav)
    seg = segs[0]
    assert seg["is_labeled"] is False
    # required(distance_m)를 채우면 True로 재계산
    r = client.patch(
        f"/api/segments/{seg['id']}/labels", json={"labels": {"distance_m": 5}}
    )
    assert r.status_code == 200
    assert r.json()["is_labeled"] is True
    # 다른 세그먼트는 그대로 False (개별 수정임을 확인)
    other = client.get(f"/api/datasets/{seg['dataset_id']}/segments").json()["items"][1]
    assert other["is_labeled"] is False


def test_patch_invalid_enum_400(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    segs = _make_segments(client, make_wav, {"distance_m": 10})
    r = client.patch(
        f"/api/segments/{segs[0]['id']}/labels", json={"labels": {"direction": "X"}}
    )
    assert r.status_code == 400
    assert "direction" in r.json()["detail"]


def test_patch_missing_segment_404(client: TestClient) -> None:
    r = client.patch("/api/segments/99999/labels", json={"labels": {"a": 1}})
    assert r.status_code == 404
