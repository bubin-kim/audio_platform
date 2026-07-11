"""GoogleDriveStorage — Drive REST API 미러 구현 (V2-3, docs/09 §3).

MirrorStorage의 미러 대상 전용: save/save_from_path/delete만 실제 구현한다.
읽기 계열(read/local_path/exists/list)은 완전 교체 모드가 비목표(09 §1)라
NotImplementedError — 읽기는 항상 로컬(MirrorStorage가 위임)이다.

공유 드라이브 전환 대비(09 §2): 모든 호출에 supportsAllDrives=true,
토큰 발급은 _get_access_token() 하나로 격리(SA 전환 시 이 함수만 교체).
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.storage.base import StorageBackend

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_API_URL = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3"
_FOLDER_MIME = "application/vnd.google-apps.folder"
# access token(수명 1h)을 만료 60초 전까지만 신뢰
_TOKEN_SAFETY_SEC = 60.0

_MEDIA_TYPES = {"csv": "text/csv", "wav": "audio/wav", "json": "application/json"}


class GoogleDriveStorage(StorageBackend):
    """Drive 미러 백엔드. transport는 테스트의 MockTransport 주입용."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        root_folder_id: str,
        timeout_sec: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._root_folder_id = root_folder_id
        self._timeout = timeout_sec
        self._transport = transport
        # 토큰 캐시
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        # 폴더 경로 → Drive 폴더 ID 캐시 (예: "exports/5" → "1AbC...")
        self._folder_cache: dict[str, str] = {}

    # --- HTTP 기반 ---

    def _client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def _get_access_token(self) -> str:
        """access token 발급/캐시. SA 전환(09 §2) 시 이 함수만 교체 대상이다."""
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        with self._client() as client:
            res = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            res.raise_for_status()
            data = res.json()
        self._access_token = data["access_token"]
        self._token_expires_at = (
            time.monotonic() + float(data.get("expires_in", 3600)) - _TOKEN_SAFETY_SEC
        )
        return self._access_token

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        content: bytes | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        # 공유 드라이브 전환 대비: 항상 supportsAllDrives (09 §2·§3).
        merged_params = {"supportsAllDrives": "true", **(params or {})}
        merged_headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            **(headers or {}),
        }
        with self._client() as client:
            res = client.request(
                method, url, params=merged_params,
                content=content, json=json_body, headers=merged_headers,
            )
            res.raise_for_status()
            return res

    # --- 폴더 해석 (경로 → 폴더 ID) ---

    @staticmethod
    def _escape(name: str) -> str:
        """Drive 검색 쿼리의 작은따옴표 이스케이프."""
        return name.replace("\\", "\\\\").replace("'", "\\'")

    def _find_child(self, name: str, parent_id: str, *, folder: bool) -> str | None:
        mime_clause = (
            f" and mimeType {'=' if folder else '!='} '{_FOLDER_MIME}'"
        )
        q = (
            f"name = '{self._escape(name)}' and '{parent_id}' in parents "
            f"and trashed = false{mime_clause}"
        )
        res = self._request(
            "GET",
            f"{DRIVE_API_URL}/files",
            params={
                "q": q,
                "fields": "files(id,name)",
                "pageSize": "1",
                "includeItemsFromAllDrives": "true",
            },
        )
        files = res.json().get("files", [])
        return files[0]["id"] if files else None

    def _resolve_folder(self, dir_path: str, *, create: bool) -> str | None:
        """논리 경로의 디렉터리 부분(예: 'exports/5')을 폴더 ID로 해석한다.

        create=True면 없는 폴더를 만들며 내려가고(save용),
        False면 없는 시점에 None을 반환한다(delete용 — 삭제가 폴더를 만들면 안 됨).
        """
        if not dir_path:
            return self._root_folder_id
        if dir_path in self._folder_cache:
            return self._folder_cache[dir_path]

        parent_id = self._root_folder_id
        walked = ""
        for part in dir_path.split("/"):
            walked = f"{walked}/{part}".lstrip("/")
            if walked in self._folder_cache:
                parent_id = self._folder_cache[walked]
                continue
            folder_id = self._find_child(part, parent_id, folder=True)
            if folder_id is None:
                if not create:
                    return None
                res = self._request(
                    "POST",
                    f"{DRIVE_API_URL}/files",
                    json_body={
                        "name": part,
                        "mimeType": _FOLDER_MIME,
                        "parents": [parent_id],
                    },
                )
                folder_id = res.json()["id"]
            self._folder_cache[walked] = folder_id
            parent_id = folder_id
        return parent_id

    # --- 미러 구현 (save/delete) ---

    def save(self, path: str, data: bytes) -> str:
        """업로드. 같은 이름이 있으면 덮어쓰기(update) — 재export 시 최신본 유지."""
        logical = path.lstrip("/")
        dir_path, _, filename = logical.rpartition("/")
        parent_id = self._resolve_folder(dir_path, create=True)
        assert parent_id is not None  # create=True는 항상 ID 반환
        mime = _MEDIA_TYPES.get(
            Path(filename).suffix.lstrip(".").lower(), "application/octet-stream"
        )

        existing_id = self._find_child(filename, parent_id, folder=False)
        if existing_id is not None:
            # 덮어쓰기: media 업로드로 내용만 교체
            self._request(
                "PATCH",
                f"{DRIVE_UPLOAD_URL}/files/{existing_id}",
                params={"uploadType": "media"},
                content=data,
                headers={"Content-Type": mime},
            )
            return logical

        # 신규: multipart/related (메타데이터 + 바이트)
        boundary = uuid.uuid4().hex
        metadata = json.dumps({"name": filename, "parents": [parent_id]})
        body = (
            (
                f"--{boundary}\r\n"
                "Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{metadata}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {mime}\r\n\r\n"
            ).encode()
            + data
            + f"\r\n--{boundary}--".encode()
        )
        self._request(
            "POST",
            f"{DRIVE_UPLOAD_URL}/files",
            params={"uploadType": "multipart"},
            content=body,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        )
        return logical

    def save_from_path(self, path: str, source: Path) -> str:
        return self.save(path, Path(source).read_bytes())

    def delete(self, path: str) -> None:
        """미러 삭제. 폴더/파일이 없으면 조용히 무시 (폴더를 만들지 않는다)."""
        logical = path.lstrip("/")
        dir_path, _, filename = logical.rpartition("/")
        parent_id = self._resolve_folder(dir_path, create=False)
        if parent_id is None:
            return  # 한 번도 미러된 적 없는 경로
        file_id = self._find_child(filename, parent_id, folder=False)
        if file_id is not None:
            self._request("DELETE", f"{DRIVE_API_URL}/files/{file_id}")

    # --- 읽기 계열: 완전 교체 모드는 비목표(09 §1) — 읽기는 항상 로컬 ---

    def read(self, path: str) -> bytes:
        raise NotImplementedError("Drive 읽기는 미지원 — 읽기는 로컬(MirrorStorage) 담당")

    def local_path(self, path: str) -> Path:
        raise NotImplementedError("Drive 읽기는 미지원 — 읽기는 로컬(MirrorStorage) 담당")

    def exists(self, path: str) -> bool:
        raise NotImplementedError("Drive 읽기는 미지원 — 읽기는 로컬(MirrorStorage) 담당")

    def list(self, prefix: str = "") -> list[str]:
        raise NotImplementedError("Drive 읽기는 미지원 — 읽기는 로컬(MirrorStorage) 담당")
