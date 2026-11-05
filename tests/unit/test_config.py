"""Unit tests for SpotifyPulse configuration and settings."""

import pytest

from spotify_pulse.config.settings import (
    DatabaseSettings,
    Settings,
    SpotifySettings,
    StorageSettings,
)


def test_default_settings_in_demo_mode() -> None:
    """Test that default settings initialize properly in demo mode without Spotify credentials."""
    settings = Settings(demo_mode=True)
    assert settings.demo_mode is True
    assert settings.project_name == "SpotifyPulse"
    assert settings.api_port == 8000
    assert settings.dashboard_port == 8501
    assert settings.spotify.client_id is None
    assert settings.spotify.client_secret is None


def test_database_settings_url_generation() -> None:
    """Test that DatabaseSettings generates expected sync and async connection URLs."""
    db = DatabaseSettings(
        host="db.internal",
        port=5433,
        user="custom_user",
        password="secret_password",
        db="warehouse_test",
    )
    expected_sync = (
        "postgresql+psycopg://custom_user:secret_password@db.internal:5433/warehouse_test"
    )
    expected_async = (
        "postgresql+psycopg_async://custom_user:secret_password@db.internal:5433/warehouse_test"
    )
    assert db.sync_url == expected_sync
    assert db.async_url == expected_async


def test_missing_credentials_fails_when_demo_mode_false() -> None:
    """Test that Settings validation fails when demo_mode is False and credentials are missing."""
    with pytest.raises(
        ValueError,
        match="SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required",
    ):
        Settings(
            demo_mode=False,
            spotify=SpotifySettings(client_id=None, client_secret=None),
        )


def test_valid_credentials_succeed_when_demo_mode_false() -> None:
    """Test that Settings validation passes when valid Spotify credentials are provided."""
    settings = Settings(
        demo_mode=False,
        spotify=SpotifySettings(
            client_id="mock_client_id_123",
            client_secret="mock_client_secret_456",
        ),
    )
    assert settings.demo_mode is False
    assert settings.spotify.client_id == "mock_client_id_123"
    assert settings.spotify.client_secret == "mock_client_secret_456"


def test_invalid_log_level_raises_error() -> None:
    """Test that an invalid log level string raises a validation error."""
    with pytest.raises(ValueError, match="Invalid log_level"):
        Settings(log_level="SUPER_CRITICAL")


def test_storage_paths_resolution() -> None:
    """Test that StorageSettings automatically resolves bronze, staging, and demo subdirectories."""
    settings = Settings()
    assert settings.storage.base_dir.name == "data"
    assert settings.storage.bronze_dir.name == "bronze"
    assert settings.storage.staging_dir.name == "staging"
    assert settings.storage.demo_dir.name == "demo"


def test_multi_tier_retention_days_configuration() -> None:
    """Test default and custom multi-tier retention policy days."""
    storage = StorageSettings()
    assert storage.bronze_retention_days == 14
    assert storage.staging_retention_days == 30
    assert storage.facts_retention_days == 730
    assert storage.snapshots_retention_days == 365

    custom_storage = StorageSettings(
        bronze_retention_days=7,
        staging_retention_days=14,
        facts_retention_days=365,
        snapshots_retention_days=180,
    )
    assert custom_storage.bronze_retention_days == 7
    assert custom_storage.staging_retention_days == 14
    assert custom_storage.facts_retention_days == 365
    assert custom_storage.snapshots_retention_days == 180


def test_spotify_settings_limits_and_token_validity() -> None:
    """Test SpotifySettings limits and 6-month token expiration defaults."""
    spotify = SpotifySettings()
    assert spotify.max_recently_played_limit == 50
    assert spotify.refresh_token_validity_days == 180

    with pytest.raises(ValueError):
        SpotifySettings(max_recently_played_limit=100)
