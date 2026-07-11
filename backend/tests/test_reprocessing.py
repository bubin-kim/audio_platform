"""재처리 안전장치 테스트 (docs/10 — 409 가드 + 라벨 승계)."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import upload_file


def _project_payload(**overrides) -> dict:
    base = {
        "name": "재처리",
        "domain": None,
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [
            {"key": "patient_id", "type": "string", "required": True},
        ],
    }
    return {**base, **overrides}


def _setup(client: TestClient, make_wav: Callable[..., Path], duration: float = 3.0):
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=duration, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    return pid, ds_id


# --- R-M1: 409 가드 ---


def test_reprocess_without_flag_409(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """기존 세그먼트가 있는 원본 재커팅은 replace_existing 없이 409."""
    _, ds_id = _setup(client, make_wav)
    assert client.post(f"/api/datasets/{ds_id}/process").status_code == 202

    r = client.post(f"/api/datasets/{ds_id}/process")
    assert r.status_code == 409
    assert "기존 세그먼트 3개" in r.json()["detail"]
    assert "replace_existing" in r.json()["detail"]
    # 누적되지 않았는지 (가드가 G2를 막음)
    assert client.get(f"/api/datasets/{ds_id}/segments").json()["total"] == 3


def test_guard_message_counts_labeled(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """가드 메시지에 라벨 있는 세그먼트 수가 표시된다."""
    _, ds_id = _setup(client, make_wav)
    client.post(
        f"/api/datasets/{ds_id}/process",
        json={"common_labels": {"patient_id": "P07"}},
    )
    r = client.post(f"/api/datasets/{ds_id}/process")
    assert r.status_code == 409
    assert "라벨 있는 것 3개" in r.json()["detail"]


def test_first_process_unaffected(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """기존 세그먼트가 없으면 가드는 발동하지 않는다 (기존 흐름 무영향)."""
    _, ds_id = _setup(client, make_wav)
    r = client.post(f"/api/datasets/{ds_id}/process")
    assert r.status_code == 202


def test_replace_flag_recorded_in_job_params(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """재처리 정책이 Job.params에 기록된다 (재현성, docs/10 §2.3)."""
    _, ds_id = _setup(client, make_wav)
    job = client.post(f"/api/datasets/{ds_id}/process").json()
    assert job["params"]["replace_existing"] is False
    assert job["params"]["inherit_labels"] is True

    job2 = client.post(
        f"/api/datasets/{ds_id}/process", json={"replace_existing": True}
    ).json()
    assert job2["params"]["replace_existing"] is True


# --- R-M2: 대체 + 라벨 승계 ---


def test_replace_deletes_old_and_inherits_labels_1to1(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """같은 파라미터 재커팅: 개별 PATCH 보정까지 1:1 승계, 누적 없음."""
    _, ds_id = _setup(client, make_wav)
    client.post(
        f"/api/datasets/{ds_id}/process",
        json={"common_labels": {"patient_id": "P01"}},
    )
    segs = client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    assert len(segs) == 3
    # 두 번째 조각만 개별 예외 보정
    client.patch(
        f"/api/segments/{segs[1]['id']}/labels", json={"labels": {"patient_id": "P99"}}
    )

    r = client.post(
        f"/api/datasets/{ds_id}/process", json={"replace_existing": True}
    )
    assert r.status_code == 202, r.text

    new_segs = client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    assert len(new_segs) == 3  # 누적 아님(대체)
    # (id는 SQLite rowid 재사용으로 같을 수 있음 — 대체 여부는 개수·시각·라벨로 검증)
    assert all(s["created_at"] >= segs[-1]["created_at"] for s in new_segs)
    labels = [s["labels"].get("patient_id") for s in new_segs]
    assert labels == ["P01", "P99", "P01"]  # 개별 보정까지 위치 그대로 승계
    assert all(s["is_labeled"] for s in new_segs)


def test_replace_inherits_1toN_when_params_change(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """사고 시나리오(docs/10 §1): 굵은 조각(라벨) → 잘게 재커팅해도 라벨 승계."""
    _, ds_id = _setup(client, make_wav)
    # 1차: 3초 간격 → 1조각, 라벨 부여
    client.post(
        f"/api/datasets/{ds_id}/process",
        json={
            "params_override": {"interval_sec": 3.0},
            "common_labels": {"patient_id": "p03"},
        },
    )
    assert client.get(f"/api/datasets/{ds_id}/segments").json()["total"] == 1

    # 2차: 1초 간격으로 대체 재커팅 (common_labels 없이!)
    r = client.post(
        f"/api/datasets/{ds_id}/process",
        json={"replace_existing": True, "params_override": {"interval_sec": 1.0}},
    )
    assert r.status_code == 202
    new_segs = client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    assert len(new_segs) == 3
    # 옛 1조각이 새 3조각 전부와 겹침 → 전부 p03 승계 (라벨 소실 없음)
    assert all(s["labels"].get("patient_id") == "p03" for s in new_segs)


def test_replace_with_inherit_off(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """inherit_labels=false면 승계하지 않는다 (명시적 포기)."""
    _, ds_id = _setup(client, make_wav)
    client.post(
        f"/api/datasets/{ds_id}/process",
        json={"common_labels": {"patient_id": "P01"}},
    )
    client.post(
        f"/api/datasets/{ds_id}/process",
        json={"replace_existing": True, "inherit_labels": False},
    )
    new_segs = client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    assert all(s["labels"] == {} for s in new_segs)
    assert all(not s["is_labeled"] for s in new_segs)


def test_replace_common_labels_override_inherited(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """승계 라벨 위에 이번 실행의 common_labels가 우선한다 (docs/10 §3)."""
    _, ds_id = _setup(client, make_wav)
    client.post(
        f"/api/datasets/{ds_id}/process",
        json={"common_labels": {"patient_id": "P01"}},
    )
    client.post(
        f"/api/datasets/{ds_id}/process",
        json={"replace_existing": True, "common_labels": {"patient_id": "P02"}},
    )
    new_segs = client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    assert all(s["labels"]["patient_id"] == "P02" for s in new_segs)


def test_replace_deletes_old_files_from_storage(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """대체 시 옛 세그먼트 파일도 Storage에서 제거된다."""
    _, ds_id = _setup(client, make_wav)
    client.post(f"/api/datasets/{ds_id}/process")
    old_paths = [
        s["storage_path"]
        for s in client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    ]
    client.post(f"/api/datasets/{ds_id}/process", json={"replace_existing": True})
    new_paths = [
        s["storage_path"]
        for s in client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    ]
    storage = client._storage
    # 새 파일은 존재, 옛 파일 중 새 목록에 없는 것은 제거됨
    assert all(storage.exists(p) for p in new_paths)
    for p in set(old_paths) - set(new_paths):
        assert not storage.exists(p)
