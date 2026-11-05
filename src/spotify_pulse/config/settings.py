"""Application configuration and environment settings management.

This module uses Pydantic Settings to validate and manage all configuration
parameters from environment variables and `.env` files. It supports both live
Spotify OAuth production execution and offline zero-credential Demo Mode.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentType(StrEnum):
    """Runtime environment classification."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"
    DEMO = "demo"


class DatabaseSettings(BaseSettings):
    """PostgreSQL Data Warehouse connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = Field(default="localhost", description="PostgreSQL host address")
    port: int = Field(default=5432, description="PostgreSQL port number")
    user: str = Field(default="postgres", description="PostgreSQL username")
    password: str = Field(default="postgres", description="PostgreSQL password")
    db: str = Field(default="spotify_pulse", description="PostgreSQL database name")
    schema_bronze: str = Field(default="bronze", description="Raw metadata schema")
    schema_staging: str = Field(default="staging", description="Staging relational schema")
    schema_gold: str = Field(default="analytics", description="Gold dimensional schema")
    pool_size: int = Field(default=10, description="SQLAlchemy connection pool size")
    max_overflow: int = Field(default=20, description="SQLAlchemy pool max overflow")

    @property
    def sync_url(self) -> str:
        """Construct standard synchronous psycopg PostgreSQL connection URL."""
        return (
            f"postgresql+psycopg://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.db}"
        )

    @property
    def async_url(self) -> str:
        """Construct asynchronous psycopg PostgreSQL connection URL."""
        return (
            f"postgresql+psycopg_async://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.db}"
        )


class SpotifySettings(BaseSettings):
    """Spotify Web API and OAuth 2.0 configuration (2026 specs)."""

    model_config = SettingsConfigDict(
        env_prefix="SPOTIFY_",
        case_sensitive=False,
        extra="ignore",
    )

    client_id: str | None = Field(
        default=None,
        description="Spotify Developer Application Client ID",
    )
    client_secret: str | None = Field(
        default=None,
        description="Spotify Developer Application Client Secret",
    )
    redirect_uri: str = Field(
        default="http://localhost:8000/auth/callback",
        description="OAuth 2.0 Redirect URI",
    )
    scopes: list[str] = Field(
        default=[
            "user-read-recently-played",
            "user-top-read",
            "user-read-private",
            "user-read-email",
            "playlist-read-private",
            "playlist-read-collaborative",
        ],
        description="Verified Spotify OAuth scopes",
    )
    api_base_url: str = Field(
        default="https://api.spotify.com/v1",
        description="Spotify Web API base endpoint",
    )
    auth_base_url: str = Field(
        default="https://accounts.spotify.com",
        description="Spotify Accounts base endpoint",
    )
    rate_limit_max_retries: int = Field(
        default=5,
        description="Maximum retry attempts on HTTP 429 status",
    )
    max_recently_played_limit: int = Field(
        default=50,
        ge=1,
        le=50,
        description="Maximum items per recently played API request",
    )
    refresh_token_validity_days: int = Field(
        default=180,
        description="Refresh token expiration window in days (June 2026 update)",
    )


class StorageSettings(BaseSettings):
    """File storage directory and multi-tier data retention configuration."""

    model_config = SettingsConfigDict(
        env_prefix="DATA_",
        case_sensitive=False,
        extra="ignore",
    )

    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[3] / "data",
        description="Root data directory",
    )
    bronze_dir: Path | None = None
    staging_dir: Path | None = None
    demo_dir: Path | None = None

    # Multi-tier retention policies
    bronze_retention_days: int = Field(
        default=14,
        ge=1,
        le=90,
        description="Bronze raw JSON retention window in days before purging",
    )
    staging_retention_days: int = Field(
        default=30,
        ge=1,
        le=180,
        description="Staging relational tables retention window in days",
    )
    facts_retention_days: int = Field(
        default=730,
        ge=30,
        le=1825,
        description="Gold fact events retention window in days (2 years)",
    )
    snapshots_retention_days: int = Field(
        default=365,
        ge=30,
        le=1095,
        description="Gold snapshots retention window in days (1 year)",
    )

    @model_validator(mode="after")
    def resolve_subdirectories(self) -> "StorageSettings":
        """Compute child storage directories if not explicitly provided."""
        if self.bronze_dir is None:
            self.bronze_dir = self.base_dir / "bronze"
        if self.staging_dir is None:
            self.staging_dir = self.base_dir / "staging"
        if self.demo_dir is None:
            self.demo_dir = self.base_dir / "demo"
        return self


class Settings(BaseSettings):
    """Central SpotifyPulse application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    project_name: str = Field(default="SpotifyPulse", description="Project application name")
    environment: EnvironmentType = Field(
        default=EnvironmentType.DEVELOPMENT,
        description="Current runtime environment",
    )
    demo_mode: bool = Field(
        default=True,
        description="Toggle offline demo mode without live Spotify credentials",
    )
    log_level: str = Field(default="INFO", description="Application log level")
    log_json_format: bool = Field(
        default=False,
        description="Format log outputs as structured JSON",
    )
    api_host: str = Field(default="0.0.0.0", description="FastAPI host binding")
    api_port: int = Field(default=8000, description="FastAPI port binding")
    dashboard_port: int = Field(default=8501, description="Streamlit dashboard port")

    # Nested configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    spotify: SpotifySettings = Field(default_factory=SpotifySettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Validate and normalize log level strings."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"Invalid log_level '{value}'. Must be one of {allowed}")
        return upper

    @model_validator(mode="after")
    def validate_spotify_credentials(self) -> "Settings":
        """Ensure Spotify credentials exist if not running in demo mode."""
        if not self.demo_mode and (not self.spotify.client_id or not self.spotify.client_secret):
            raise ValueError(
                "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required "
                "when DEMO_MODE is False. To run offline without credentials, "
                "set DEMO_MODE=True."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve cached application settings singleton."""
    return Settings()
