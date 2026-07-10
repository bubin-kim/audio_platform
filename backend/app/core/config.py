"""애플리케이션 설정.

모든 경로·설정값은 여기(그리고 .env)에서만 읽는다. 코드에 하드코딩 금지(CLAUDE.md §5).
SQLite→PostgreSQL 전환은 DATABASE_URL 교체만으로 이뤄진다(P3).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 디렉터리 (이 파일 기준 2단계 위: core -> app -> backend)
BACKEND_DIR = Path(__file__).resolve().parents[2]
# 저장소 루트 (backend/의 부모)
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """환경변수/기본값 로드. .env 파일이 있으면 덮어쓴다."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 앱 ---
    app_name: str = "Audio Dataset Management Platform"
    api_prefix: str = "/api"
    # 프론트엔드 개발 서버 (CORS 허용 대상)
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- DB (MVP: SQLite / V2: PostgreSQL은 이 URL만 교체) ---
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'audio_platform.db'}"

    # --- 로컬 저장소 경로 (V2: Drive로 대체되므로 Storage 인터페이스 경유) ---
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def segments_dir(self) -> Path:
        return self.data_dir / "segments"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴. 의존성 주입·모듈 어디서든 이 함수로 접근한다."""
    return Settings()
