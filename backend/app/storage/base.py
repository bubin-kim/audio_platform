"""StorageBackend 인터페이스 (P2·P3).

Service는 파일이 Local에 있는지 Drive에 있는지 모른 채 이 인터페이스만 부른다.
V2에서 GoogleDriveStorage로 교체해도 Service 코드는 손대지 않는다(02 §6.1).

경로 규약: 모든 `path`는 저장소 루트 기준 **논리 경로**(예: "uploads/2/rec.wav").
로컬 FS 절대경로를 직접 다루지 않는다(CLAUDE.md §5, 오디오 접근은 항상 Storage 경유).
"""

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """저장소 추상 인터페이스."""

    @abstractmethod
    def save(self, path: str, data: bytes) -> str:
        """바이트를 논리 경로에 저장하고, 저장된 논리 경로를 반환한다."""

    @abstractmethod
    def save_from_path(self, path: str, source: Path) -> str:
        """이미 존재하는 파일(source)을 논리 경로로 저장(복사)한다.

        업로드 임시파일이나 커팅이 만든 임시 wav를 저장소에 넣을 때 쓴다.
        대용량 파일에서 메모리에 전부 올리지 않기 위한 경로.
        """

    @abstractmethod
    def read(self, path: str) -> bytes:
        """논리 경로의 내용을 바이트로 읽는다."""

    @abstractmethod
    def local_path(self, path: str) -> Path:
        """오디오 라이브러리가 읽을 수 있는 실제 FS 경로를 반환한다.

        Local이면 실제 경로를 그대로, Drive(V2)면 임시로 내려받은 경로를 준다.
        audio/ 는 이 반환 경로(순수 Path)만 받으므로 Storage 종류를 모른다(P2).
        """

    @abstractmethod
    def exists(self, path: str) -> bool:
        """논리 경로에 파일이 있는지."""

    @abstractmethod
    def delete(self, path: str) -> None:
        """논리 경로의 파일을 삭제한다(없으면 무시)."""

    @abstractmethod
    def list(self, prefix: str = "") -> list[str]:
        """prefix로 시작하는 논리 경로 목록을 반환한다."""
