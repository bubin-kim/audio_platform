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

    # --- Notion 연동 (V2-1, docs/07 §3) ---
    # 두 키가 모두 있어야 활성화. 없으면 구독자 미등록 = MVP와 동일 동작(P4).
    notion_api_key: str = ""
    notion_database_id: str = ""
    notion_api_version: str = "2022-06-28"
    notion_timeout_sec: float = 10.0

    @property
    def notion_enabled(self) -> bool:
        """Notion 구독자를 등록할지 여부 (토큰 + DB id 둘 다 필요)."""
        return bool(self.notion_api_key and self.notion_database_id)

    # --- Google Drive 미러 (V2-3, docs/09 §4) ---
    # 네 값이 모두 있어야 활성화. 없으면 LocalStorage 그대로 = MVP와 동일(P4).
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_refresh_token: str = ""
    drive_root_folder_id: str = ""
    # 미러 대상 prefix. wav가 필요해지면 "segments" 추가만으로 활성화(코드 변경 0).
    drive_mirror_prefixes: list[str] = ["exports"]
    drive_timeout_sec: float = 30.0

    # --- CSV export 경로 패턴 (V2-5, docs/11 §2) ---
    # 플레이스홀더: {project} {dataset} {version} {date} {project_id} {dataset_id}
    # exports/ 밖으로 바꾸면 Drive 미러(DRIVE_MIRROR_PREFIXES) 대상에서 벗어남에 주의.
    export_path_pattern: str = "exports/{project}/{date}_{dataset}.csv"

    @property
    def drive_enabled(self) -> bool:
        """Drive 미러를 켤지 여부 (OAuth 3종 + 루트 폴더 ID 모두 필요)."""
        return bool(
            self.google_oauth_client_id
            and self.google_oauth_client_secret
            and self.google_oauth_refresh_token
            and self.drive_root_folder_id
        )

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
