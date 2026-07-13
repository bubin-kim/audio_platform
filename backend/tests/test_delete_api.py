"""삭제 API 테스트 (docs/12 B1) + 중복 업로드 409 (B2)."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import upload_file


def _project_payload(name: str = "삭제테스트") -> dict:
    return {
        "name": name,
        "domain": None,
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [],
    }


def _setup_with_segments(client: TestClient, make_wav: Callable[..., Path]):
    """프로젝트 → 업로드 → 커팅 → export까지 만들어 삭제 대상 풀세트 준비."""
    pid = client.post("/api/projects", json=_project_payload()).json()["id"]
    wav = make_wav(duration_sec=3.0, name="rec.wav")
    up = upload_file(client, pid, wav, "rec.wav")
    ds_id, sf_id = up["dataset_id"], up["sources"][0]["id"]
    client.post(f"/api/datasets/{ds_id}/process")
    client.get(f"/api/datasets/{ds_id}/export")
    return pid, ds_id, sf_id


# --- 세그먼트 삭제 ---


def test_delete_segment(client: TestClient, make_wav: Callable[..., Path]) -> None:
    _, ds_id, _ = _setup_with_segments(client, make_wav)
    seg = client.get(f"/api/datasets/{ds_id}/segments").json()["items"][0]

    r = client.delete(f"/api/segments/{seg['id']}")
    assert r.status_code == 204
    assert not client._storage.exists(seg["storage_path"])  # 파일도 제거
    assert client.get(f"/api/datasets/{ds_id}/segments").json()["total"] == 2


def test_delete_segment_404(client: TestClient) -> None:
    assert client.delete("/api/segments/99999").status_code == 404


# --- 원본 삭제 ---


def test_delete_source_file_blocked_by_refs_then_ok(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    _, ds_id, sf_id = _setup_with_segments(client, make_wav)

    # 세그먼트가 참조 중 → 409
    r = client.delete(f"/api/source-files/{sf_id}")
    assert r.status_code == 409
    assert "세그먼트 3개" in r.json()["detail"]

    # 세그먼트 정리 후 → 204
    for s in client.get(f"/api/datasets/{ds_id}/segments").json()["items"]:
        client.delete(f"/api/segments/{s['id']}")
    r = client.delete(f"/api/source-files/{sf_id}")
    assert r.status_code == 204
    assert not client._storage.exists(f"uploads/{ds_id}/rec.wav")


# --- 데이터셋/프로젝트 삭제 (confirm 필수) ---


def test_delete_dataset_requires_matching_confirm(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    _, ds_id, _ = _setup_with_segments(client, make_wav)
    ds_name = client.get(f"/api/datasets/{ds_id}").json()["name"]

    r = client.delete(f"/api/datasets/{ds_id}?confirm=틀린이름")
    assert r.status_code == 400
    assert "확인 이름" in r.json()["detail"]

    r = client.delete(f"/api/datasets/{ds_id}?confirm={ds_name}")
    assert r.status_code == 204
    assert client.get(f"/api/datasets/{ds_id}").status_code == 404
    # 파일 전부 정리 (세그먼트 + 원본 + export CSV)
    assert client._storage.list(f"segments/{ds_id}") == []
    assert client._storage.list(f"uploads/{ds_id}") == []


def test_delete_project_cascades_everything(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    pid, ds_id, _ = _setup_with_segments(client, make_wav)

    r = client.delete(f"/api/projects/{pid}?confirm=삭제테스트")
    assert r.status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.get(f"/api/datasets/{ds_id}").status_code == 404
    assert client._storage.list(f"segments/{ds_id}") == []


# --- B2: 중복 업로드 차단 ---


def test_duplicate_upload_409_and_file_intact(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """같은 파일명 재업로드 → 409, 기존 파일은 훼손되지 않음 (docs/12 B2)."""
    pid = client.post("/api/projects", json=_project_payload("중복")).json()["id"]
    wav1 = make_wav(duration_sec=2.0, name="rec.wav")
    up = upload_file(client, pid, wav1, "rec.wav")
    ds_id = up["dataset_id"]
    original = client._storage.read(f"uploads/{ds_id}/rec.wav")

    # 내용이 다른 같은 이름 파일로 재업로드 시도
    wav2 = make_wav(duration_sec=1.0, sample_rate=8000, name="rec2.wav")
    with wav2.open("rb") as f:
        r = client.post(
            "/api/uploads",
            data={"project_id": pid, "dataset_id": ds_id},
            files={"files": ("rec.wav", f, "audio/wav")},
        )
    assert r.status_code == 409
    assert "이미 이 Dataset에 업로드" in r.json()["detail"]
    # 파일이 덮어써지지 않음
    assert client._storage.read(f"uploads/{ds_id}/rec.wav") == original
    # row도 1개 그대로
    assert len(up["sources"]) == 1