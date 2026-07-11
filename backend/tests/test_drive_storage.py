"""Drive 미러 테스트 (V2-2 — docs/09 §6). 실제 Drive 불필요(MockTransport)."""

import json
from pathlib import Path

import httpx
import pytest

import app.storage.mirror as mirror_module
from app.core.config import Settings
from app.storage import build_storage
from app.storage.drive import GoogleDriveStorage
from app.storage.local import LocalStorage
from app.storage.mirror import MirrorStorage

ROOT_ID = "root-folder-id"


class _DriveRecorder:
    """가짜 Google API: 토큰·폴더 검색/생성·업로드·삭제를 기록·응답한다."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        # (name, parent) → id. 폴더/파일 존재 시뮬레이션.
        self.folders: dict[tuple[str, str], str] = {}
        self.files: dict[tuple[str, str], str] = {}
        self._seq = 0

    def _new_id(self, kind: str) -> str:
        self._seq += 1
        return f"{kind}-{self._seq}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)

        if "oauth2.googleapis.com/token" in url:
            self.token_calls += 1
            return httpx.Response(
                200, json={"access_token": f"tok-{self.token_calls}", "expires_in": 3600}
            )

        if request.method == "GET" and "/drive/v3/files" in url:
            # 검색 쿼리 파싱: name = 'X' and 'PARENT' in parents ... mimeType =/!= folder
            q = request.url.params["q"]
            name = q.split("name = '")[1].split("'")[0]
            parent = q.split("'")[1] if "' in parents" not in q.split("name = '")[0] else None
            parent = q.split(" and '")[1].split("' in parents")[0]
            is_folder_query = "mimeType = '" in q
            table = self.folders if is_folder_query else self.files
            fid = table.get((name, parent))
            return httpx.Response(
                200, json={"files": [{"id": fid, "name": name}] if fid else []}
            )

        if request.method == "POST" and url.startswith(
            "https://www.googleapis.com/drive/v3/files"
        ):
            body = json.loads(request.content.decode())
            fid = self._new_id("folder")
            self.folders[(body["name"], body["parents"][0])] = fid
            return httpx.Response(200, json={"id": fid})

        if request.method == "POST" and "/upload/drive/v3/files" in url:
            # multipart 신규 업로드 — 메타데이터 파트에서 name/parents 추출
            raw = request.content.decode(errors="ignore")
            meta = json.loads(raw.split("\r\n\r\n")[1].split("\r\n")[0])
            fid = self._new_id("file")
            self.files[(meta["name"], meta["parents"][0])] = fid
            return httpx.Response(200, json={"id": fid})

        if request.method == "PATCH" and "/upload/drive/v3/files/" in url:
            return httpx.Response(200, json={"id": url.rsplit("/", 1)[-1].split("?")[0]})

        if request.method == "DELETE" and "/drive/v3/files/" in url:
            return httpx.Response(204)

        return httpx.Response(404, json={"error": f"unhandled {request.method} {url}"})


def _drive(rec: _DriveRecorder) -> GoogleDriveStorage:
    return GoogleDriveStorage(
        client_id="cid",
        client_secret="cs",
        refresh_token="rt",
        root_folder_id=ROOT_ID,
        timeout_sec=5.0,
        transport=httpx.MockTransport(rec),
    )


# --- GoogleDriveStorage 단위 ---


def test_upload_creates_folder_chain_and_multipart() -> None:
    rec = _DriveRecorder()
    _drive(rec).save("exports/5/metadata.csv", b"a,b\n1,2\n")

    # 폴더 체인 생성: exports(루트 아래) → 5(exports 아래)
    assert ("exports", ROOT_ID) in rec.folders
    exports_id = rec.folders[("exports", ROOT_ID)]
    assert ("5", exports_id) in rec.folders
    # 파일이 5 폴더 아래 생성
    five_id = rec.folders[("5", exports_id)]
    assert ("metadata.csv", five_id) in rec.files
    # 업로드 요청 검증: multipart/related + supportsAllDrives + Bearer
    upload = [r for r in rec.requests if "/upload/" in str(r.url)][0]
    assert upload.headers["Content-Type"].startswith("multipart/related")
    assert upload.headers["Authorization"] == "Bearer tok-1"
    assert upload.url.params["supportsAllDrives"] == "true"
    assert b"a,b\n1,2\n" in upload.content


def test_upload_same_name_overwrites_via_patch() -> None:
    rec = _DriveRecorder()
    d = _drive(rec)
    d.save("exports/5/metadata.csv", b"v1")
    d.save("exports/5/metadata.csv", b"v2")  # 같은 이름 → PATCH update

    patches = [r for r in rec.requests if r.method == "PATCH"]
    assert len(patches) == 1
    assert patches[0].content == b"v2"
    assert patches[0].url.params["uploadType"] == "media"
    # 신규 multipart 업로드는 1회뿐
    posts = [r for r in rec.requests if r.method == "POST" and "/upload/" in str(r.url)]
    assert len(posts) == 1


def test_token_cached_across_calls() -> None:
    rec = _DriveRecorder()
    d = _drive(rec)
    d.save("exports/1/a.csv", b"x")
    d.save("exports/1/b.csv", b"y")
    assert rec.token_calls == 1  # 두 번째 호출은 캐시 사용


def test_delete_does_not_create_folders() -> None:
    rec = _DriveRecorder()
    d = _drive(rec)
    d.delete("exports/9/none.csv")  # 미러된 적 없는 경로
    assert rec.folders == {}  # 폴더가 생기지 않아야 함
    assert not [r for r in rec.requests if r.method == "DELETE"]


def test_delete_removes_existing_file() -> None:
    rec = _DriveRecorder()
    d = _drive(rec)
    d.save("exports/5/metadata.csv", b"x")
    d.delete("exports/5/metadata.csv")
    deletes = [r for r in rec.requests if r.method == "DELETE"]
    assert len(deletes) == 1


def test_read_paths_not_supported() -> None:
    d = _drive(_DriveRecorder())
    with pytest.raises(NotImplementedError):
        d.read("exports/1/a.csv")


# --- MirrorStorage 단위 ---


@pytest.fixture
def sync_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    """미러 스레드를 동기 실행으로 — 테스트 결정성."""
    monkeypatch.setattr(mirror_module, "_spawn", lambda target, **kw: target(**kw))


def _mirror_setup(tmp_path: Path, prefixes: list[str] | None = None):
    rec = _DriveRecorder()
    local = LocalStorage(root=tmp_path / "data")
    mirror = MirrorStorage(
        local=local, mirror=_drive(rec), prefixes=prefixes or ["exports"]
    )
    return mirror, local, rec


def test_mirror_exports_only(tmp_path: Path, sync_spawn: None) -> None:
    mirror, local, rec = _mirror_setup(tmp_path)

    mirror.save("exports/5/metadata.csv", b"csv")
    mirror.save("segments/5/a.wav", b"wav")  # 기본 설정에선 미러 안 됨
    mirror.save("uploads/5/rec.wav", b"orig")

    # 로컬엔 셋 다 저장
    assert local.exists("exports/5/metadata.csv")
    assert local.exists("segments/5/a.wav")
    assert local.exists("uploads/5/rec.wav")
    # Drive엔 exports만
    uploaded_names = [k[0] for k in rec.files]
    assert uploaded_names == ["metadata.csv"]


def test_mirror_prefix_config_enables_segments(
    tmp_path: Path, sync_spawn: None
) -> None:
    """설정으로 segments 추가 시 wav도 미러 — 코드 변경 0 검증(09 §1)."""
    mirror, _, rec = _mirror_setup(tmp_path, prefixes=["exports", "segments"])
    mirror.save("segments/5/a.wav", b"wav")
    assert [k[0] for k in rec.files] == ["a.wav"]


def test_mirror_delete(tmp_path: Path, sync_spawn: None) -> None:
    mirror, local, rec = _mirror_setup(tmp_path)
    mirror.save("exports/5/metadata.csv", b"csv")
    mirror.delete("exports/5/metadata.csv")
    assert not local.exists("exports/5/metadata.csv")
    assert [r for r in rec.requests if r.method == "DELETE"]


def test_mirror_failure_does_not_break_save(
    tmp_path: Path, sync_spawn: None
) -> None:
    """Drive가 500이어도 로컬 save는 성공한다 (본 흐름 보호, 09 §3)."""
    local = LocalStorage(root=tmp_path / "data")
    broken = GoogleDriveStorage(
        client_id="c", client_secret="s", refresh_token="r",
        root_folder_id=ROOT_ID, timeout_sec=5.0,
        transport=httpx.MockTransport(lambda req: httpx.Response(500, json={})),
    )
    mirror = MirrorStorage(local=local, mirror=broken, prefixes=["exports"])
    logical = mirror.save("exports/1/m.csv", b"x")  # 예외 없이 통과해야 함
    assert logical == "exports/1/m.csv"
    assert local.read("exports/1/m.csv") == b"x"


def test_mirror_read_paths_delegate_to_local(tmp_path: Path, sync_spawn: None) -> None:
    mirror, local, rec = _mirror_setup(tmp_path)
    mirror.save("exports/1/m.csv", b"x")
    assert mirror.read("exports/1/m.csv") == b"x"
    assert mirror.exists("exports/1/m.csv")
    assert mirror.list("exports") == ["exports/1/m.csv"]
    assert mirror.local_path("exports/1/m.csv") == local.local_path("exports/1/m.csv")
    # 읽기 계열은 Drive에 GET 요청을 만들지 않는다 (upload/token 외 GET 없음 확인)
    reads_to_drive = [
        r for r in rec.requests
        if r.method == "GET" and "drive" in str(r.url) and "files?" not in str(r.url)
    ]
    assert reads_to_drive == []


# --- get_storage 분기 ---


def test_build_storage_branch(tmp_path: Path) -> None:
    base = {"_env_file": None, "data_dir": tmp_path / "d"}
    s_off = Settings(**base)
    assert isinstance(build_storage(s_off), LocalStorage)

    s_on = Settings(
        **base,
        google_oauth_client_id="a", google_oauth_client_secret="b",
        google_oauth_refresh_token="c", drive_root_folder_id="d",
    )
    assert isinstance(build_storage(s_on), MirrorStorage)
