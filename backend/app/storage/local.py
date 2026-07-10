"""LocalStorage — 로컬 파일시스템 구현 (MVP).

논리 경로를 저장소 루트(settings.data_dir) 아래 실제 경로로 매핑한다.
경로 탈출(../ 등)을 막아 루트 밖으로 나가지 못하게 한다.
"""

import shutil
from pathlib import Path

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        """논리 경로 → 실제 경로. 루트 밖으로 벗어나면 거부."""
        # 선행 슬래시 제거(항상 루트 상대 경로로 취급).
        rel = Path(path.lstrip("/"))
        full = (self._root / rel).resolve()
        if not full.is_relative_to(self._root):
            raise ValueError(f"경로가 저장소 루트를 벗어납니다: {path}")
        return full

    def save(self, path: str, data: bytes) -> str:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return path

    def save_from_path(self, path: str, source: Path) -> str:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, full)
        return path

    def read(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def local_path(self, path: str) -> Path:
        # 로컬은 논리 경로가 곧 실제 경로.
        return self._resolve(path)

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def delete(self, path: str) -> None:
        full = self._resolve(path)
        full.unlink(missing_ok=True)

    def list(self, prefix: str = "") -> list[str]:
        base = self._resolve(prefix) if prefix else self._root
        if not base.exists():
            return []
        results: list[str] = []
        for p in base.rglob("*"):
            if p.is_file():
                results.append(str(p.relative_to(self._root)))
        return sorted(results)
