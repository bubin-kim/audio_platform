"""재사용성 검증 (M10 — PRD 성공기준 5, 가장 중요).

차량음이 아닌 도메인(심음)을 **Project 설정만으로** 새로 만들어
업로드→커팅→라벨→세그먼트→CSV의 전 과정이 같은 코드로 도는지 확인한다.

이 파일이 플랫폼 코드(app/)를 단 한 줄도 바꾸지 않고 통과한다는 사실 자체가
"새 도메인 추가 = 설정 추가"(P1/R1)의 증거이자 회귀 방지선이다.
"""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import upload_file

# 심음 도메인 — 차량음과 커팅 파라미터·파일명 규칙·라벨 스키마가 전부 다르다.
# 다른 것은 이 설정(JSON)뿐이고, 코드는 동일하다.
HEART_PROJECT = {
    "name": "심음 판막별 수집",
    "domain": "heart",
    "cutting_mode": "fixed_interval",
    "cutting_params": {"interval_sec": 2.0},
    "naming_pattern": "{patient_id}_{valve}_{seq:03d}",
    "label_schema": [
        {"key": "patient_id", "type": "string", "required": True},
        {
            "key": "valve",
            "type": "enum",
            "options": ["mitral", "aortic", "tricuspid", "pulmonary"],
            "required": True,
        },
    ],
    "target_duration_sec": 1800,
}

VEHICLE_PROJECT = {
    "name": "차량음",
    "domain": "vehicle",
    "cutting_mode": "fixed_interval",
    "cutting_params": {"interval_sec": 3.0},
    "naming_pattern": "{date}_{distance_m}m_{seq:03d}",
    "label_schema": [
        {"key": "distance_m", "type": "number", "required": True},
    ],
}


def test_heart_domain_full_pipeline_config_only(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """심음 프로젝트: 설정만으로 업로드→커팅→파일명→라벨→CSV 전 과정 동작."""
    pid = client.post("/api/projects", json=HEART_PROJECT).json()["id"]

    # 심음은 저샘플레이트가 흔하다 — 4kHz 6초 녹음
    wav = make_wav(duration_sec=6.0, sample_rate=4000, name="heart_rec.wav")
    ds_id = upload_file(client, pid, wav, "heart_rec.wav")["dataset_id"]

    # 커팅 (심음 라벨 일괄 부여) → 2초 간격 = 3조각
    r = client.post(
        f"/api/datasets/{ds_id}/process",
        json={"common_labels": {"patient_id": "P01", "valve": "mitral"}},
    )
    assert r.status_code == 202, r.text
    job = client.get(f"/api/jobs/{r.json()['id']}").json()
    assert job["status"] == "done", job
    assert job["progress"] == 3

    # 파일명이 심음 규칙대로 (P01_mitral_001.wav ...)
    segs = client.get(f"/api/datasets/{ds_id}/segments").json()["items"]
    assert [s["filename"] for s in segs] == [
        "P01_mitral_001.wav",
        "P01_mitral_002.wav",
        "P01_mitral_003.wav",
    ]
    assert all(s["labels"] == {"patient_id": "P01", "valve": "mitral"} for s in segs)
    assert all(s["is_labeled"] for s in segs)
    assert all(s["sample_rate"] == 4000 for s in segs)

    # 개별 예외 보정 — 마지막 조각만 aortic
    r = client.patch(
        f"/api/segments/{segs[-1]['id']}/labels", json={"labels": {"valve": "aortic"}}
    )
    assert r.status_code == 200
    assert r.json()["labels"]["valve"] == "aortic"

    # 심음 스키마 위반은 400 (설정이 검증을 이끈다)
    r = client.patch(
        f"/api/segments/{segs[0]['id']}/labels", json={"labels": {"valve": "unknown"}}
    )
    assert r.status_code == 400

    # CSV — 라벨 컬럼이 심음 스키마(patient_id, valve)로 나온다
    assert client.get(f"/api/datasets/{ds_id}/export").status_code == 202
    csv_text = client.get(f"/api/datasets/{ds_id}/export/download").text
    header = csv_text.splitlines()[0]
    assert header.endswith("patient_id,valve")
    assert "P01_mitral_001.wav" in csv_text
    assert "aortic" in csv_text  # 예외 보정 반영


def test_two_domains_coexist_same_code(
    client: TestClient, make_wav: Callable[..., Path]
) -> None:
    """차량음·심음 프로젝트가 같은 서버에서 동시에, 서로 다른 설정으로 동작."""
    vid = client.post("/api/projects", json=VEHICLE_PROJECT).json()["id"]
    hid = client.post("/api/projects", json=HEART_PROJECT).json()["id"]

    v_wav = make_wav(duration_sec=6.0, sample_rate=16000, name="car.wav")
    h_wav = make_wav(duration_sec=6.0, sample_rate=4000, name="heart.wav")
    v_ds = upload_file(client, vid, v_wav, "car.wav")["dataset_id"]
    h_ds = upload_file(client, hid, h_wav, "heart.wav")["dataset_id"]

    # 같은 엔드포인트·같은 코드 — 설정이 달라 결과(조각 수·파일명)가 달라진다
    r_v = client.post(
        f"/api/datasets/{v_ds}/process", json={"common_labels": {"distance_m": 20}}
    )
    r_h = client.post(
        f"/api/datasets/{h_ds}/process",
        json={"common_labels": {"patient_id": "P02", "valve": "tricuspid"}},
    )
    assert r_v.status_code == 202 and r_h.status_code == 202

    v_segs = client.get(f"/api/datasets/{v_ds}/segments").json()["items"]
    h_segs = client.get(f"/api/datasets/{h_ds}/segments").json()["items"]
    assert len(v_segs) == 2  # 6초 / 3초
    assert len(h_segs) == 3  # 6초 / 2초
    assert v_segs[0]["filename"].endswith("_20m_001.wav")
    assert h_segs[0]["filename"] == "P02_tricuspid_001.wav"

    # 전체 stats에 두 도메인이 함께 집계된다
    stats = client.get("/api/stats").json()
    assert stats["total_segments"] == 5
    names = {p["name"]: p["segment_count"] for p in stats["per_project"]}
    assert names["차량음"] == 2
    assert names["심음 판막별 수집"] == 3
    # 샘플레이트 분포에 두 도메인의 SR이 모두 나타난다
    assert set(stats["sample_rate_distribution"]) == {"16000", "4000"}
