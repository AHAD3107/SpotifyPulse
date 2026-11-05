"""Pytest fixtures and configuration for SpotifyPulse test suite."""

import pytest

from spotify_pulse.config.settings import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests run in isolated demo mode environment by default."""
    monkeypatch.setenv("SPOTIFY_PULSE_DEMO_MODE", "true")
    monkeypatch.setenv("SPOTIFY_PULSE_ENVIRONMENT", "testing")
    monkeypatch.setenv("SPOTIFY_PULSE_LOG_LEVEL", "DEBUG")


@pytest.fixture
def test_settings() -> Settings:
    """Provide a fresh instance of Settings configured for testing."""
    return Settings(
        demo_mode=True,
        environment="testing",
        log_level="DEBUG",
    )
