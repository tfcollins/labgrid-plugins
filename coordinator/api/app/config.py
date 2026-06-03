from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    coordinator_address: str = "coordinator:20408"
    api_name: str = "web-dashboard"
    database_path: str = "/data/coordinator_history.db"

    session_ttl_hours: int = 24
    session_cookie_name: str = "lg_session"
    session_cookie_secure: bool = False

    oidc_issuer_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_auto_provision: bool = False

    recordings_dir: str = "/data/recordings"
    recording_retention_days: int = 30
    recording_max_bytes_per_place: int = 1024 * 1024 * 1024

    board_catalog_path: str = str(Path(__file__).resolve().parent / "board_catalog.yaml")

    model_config = {"env_prefix": "LG_"}


settings = Settings()
