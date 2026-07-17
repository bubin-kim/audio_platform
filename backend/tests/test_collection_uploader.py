"""수집 진행률(개수) + 업로더 기록 테스트 (V2-7 — docs/15)."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import upload_file


def _project(client: TestClient, *, target: int | None = None, name: str = "수집") -> int:
    p = {
        "name": name,
        "domain": None,
        "cutting_mode": "fixed_interval",
        "cutting_params": {"interval_sec": 1.0},
        "naming_pattern": "{date}_{seq:03d}",
        "label_schema": [],
    }
    if target is not None:
        p["target_segment_count"] = target
    r = client.post("/api/projects", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload_as(
    client: TestClient, project_id: int, wav: Path, name: str, uploaded_by: str | None
) -> dict:
    data: dict = {"project_id": project_id}
    if uploaded_by is not None:
        data["uploaded_by"] = uploaded_by
    with wav.open("rb") as f:
        r = client.post(
            "/api/uploads", data=data, files={"files": (name, f, "audio/wav")}
        )
    assert r.status_code == 201, r.text
    return r.json()


# --- A. 수집 진행률 (collection_progress) ---


def test_collection_progress_with_target(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """목표 10 설정 → 3초/1초 커팅 = 3조각 → 3/10 = 30%."""
    pid = _project(client, target=10)
    assert (
        client.get(f"/api/projects/{pid}").json()["target_segment_count"] == 10
    )
    wav = make_wav(duration_sec=3.0, name="rec.wav")
    ds_id = upload_file(client, pid, wav, "rec.wav")["dataset_id"]
    client.post(f"/api/datasets/{ds_id}/process")

    cp = client.get(f"/api/stats?project_id={pid}").json()["collection_progress"]
    assert cp == {"collected": 3, "target": 10, "ratio": 0.3}


def test_collection_progress_without_target(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """목표 미설정 → target/ratio는 null (게이지 미표시) — 기존 프로젝트 무영향."""
    pid = _project(client)
    cp = client.get(f"/api/stats?project_id={pid}").json()["collection_progress"]
    assert cp == {"collected": 0, "target": None, "ratio": None}


def test_collection_progress_global_sums_targets(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """전체 조회는 목표 설정된 프로젝트들의 합 (upload_progress와 같은 규칙)."""
    _project(client, target=10, name="A")
    _project(client, target=20, name="B")
    _project(client, name="C(목표 없음)")
    cp = client.get("/api/stats").json()["collection_progress"]
    assert cp["target"] == 30


def test_target_segment_count_patch(client: TestClient) -> None:
    pid = _project(client)
    r = client.patch(f"/api/projects/{pid}", json={"target_segment_count": 11520})
    assert r.status_code == 200
    assert r.json()["target_segment_count"] == 11520


# --- B. 업로더 기록 (uploaded_by) ---


def test_uploaded_by_recorded(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """업로드 시 이름 → SourceRead·최근 업로드에 남는다."""
    pid = _project(client)
    wav = make_wav(duration_sec=1.0, name="a.wav")
    res = _upload_as(client, pid, wav, "a.wav", "김연구")
    assert res["sources"][0]["uploaded_by"] == "김연구"

    recent = client.get(f"/api/stats?project_id={pid}").json()["recent_uploads"]
    assert recent[0]["uploaded_by"] == "김연구"


def test_uploaded_by_optional_and_blank_normalized(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """미기재·공백은 null로 — 기존 업로드 흐름 무영향."""
    pid = _project(client)
    r1 = _upload_as(client, pid, make_wav(duration_sec=1.0, name="b.wav"), "b.wav", None)
    assert r1["sources"][0]["uploaded_by"] is None
    r2 = _upload_as(client, pid, make_wav(duration_sec=1.0, name="c.wav"), "c.wav", "   ")
    assert r2["sources"][0]["uploaded_by"] is None


def test_uploaded_by_survives_source_delete(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """원본을 삭제해도 업로드 이력의 이름은 남는다 (docs/15 §2)."""
    pid = _project(client)
    res = _upload_as(
        client, pid, make_wav(duration_sec=1.0, name="d.wav"), "d.wav", "박연구"
    )
    sid = res["sources"][0]["id"]
    assert client.delete(f"/api/source-files/{sid}").status_code == 204
    recent = client.get(f"/api/stats?project_id={pid}").json()["recent_uploads"]
    assert recent[0]["filename"] == "d.wav"
    assert recent[0]["uploaded_by"] == "박연구"
