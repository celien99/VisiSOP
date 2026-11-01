from pathlib import Path

from pydantic import HttpUrl, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_PREFIX: str = "/api"
    FRONTEND_HOST: str = "http://localhost:5173"
    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    DATABASE_URL: PostgresDsn
    EVIDENCE_DIR: Path = Path("../evidence")
    RUNTIME_STALE_AFTER_MS: int = 15000
    EXECUTION_ACCEPT_WINDOW_MS: int = 600000
    OUTBOX_POLL_MS: int = 200
    TIMEOUT_POLL_MS: int = 1000
    WORKERS_ENABLED: bool = True
    TRAINING_DIR: Path = Path("../training")
    TRAINING_ENABLED: bool = True
    TRAINING_EPOCHS: int = 50
    TRAINING_IMGSZ: int = 640
    TRAINING_DEVICE: str = "0"
    TRAINING_POLL_MS: int = 2000
    MODEL_POLL_S: int = 10
    MAX_VIDEO_MB: int = 512
    RUNTIME_PROJECT_DIR: Path = Path("../runtime")
    TRAINING_BASE_MODEL: str = "models/yolo11n.pt"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: str | PostgresDsn) -> str:
        database_url = str(value)
        for scheme in ("postgres://", "postgresql://"):
            if database_url.startswith(scheme):
                return database_url.replace(scheme, "postgresql+psycopg://", 1)
        return database_url


settings = Settings()  # type: ignore # ty: ignore[unused-ignore-comment]
