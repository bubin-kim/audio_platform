"""GoogleDriveStorage — V2 자리 (빈 골격, P4).

MVP에서는 구현하지 않는다. StorageBackend를 만족하는 클래스가 "여기 온다"는 것만
가시화한다. V2에서 Drive MCP로 채우면 Service는 한 줄도 바뀌지 않는다(02 §6.1).
"""

from pathlib import Path

from app.storage.base import StorageBackend


class GoogleDriveStorage(StorageBackend):  # pragma: no cover - V2 자리
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        raise NotImplementedError("GoogleDriveStorage는 V2에서 구현됩니다.")

    def save(self, path: str, data: bytes) -> str:
        raise NotImplementedError

    def save_from_path(self, path: str, source: Path) -> str:
        raise NotImplementedError

    def read(self, path: str) -> bytes:
        raise NotImplementedError

    def local_path(self, path: str) -> Path:
        raise NotImplementedError

    def exists(self, path: str) -> bool:
        raise NotImplementedError

    def delete(self, path: str) -> None:
        raise NotImplementedError

    def list(self, prefix: str = "") -> list[str]:
        raise NotImplementedError
