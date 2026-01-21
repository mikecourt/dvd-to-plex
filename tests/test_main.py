"""Tests for main application entry point."""

from pathlib import Path

import pytest

from dvdtoplex.config import Config
from dvdtoplex.main import Application


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """Create a test configuration."""
    return Config(
        workspace_dir=tmp_path / "workspace",
        plex_movies_dir=tmp_path / "movies",
        plex_tv_dir=tmp_path / "tv",
        web_host="127.0.0.1",
        web_port=8080,
    )


@pytest.mark.asyncio
async def test_application_creates_directories(config: Config) -> None:
    """Test that the application creates workspace directories."""
    app = Application(config)
    await app._ensure_directories()

    assert config.workspace_dir.exists()
    assert config.staging_dir.exists()
    assert config.encoding_dir.exists()


@pytest.mark.asyncio
async def test_application_stop_logs_shutdown(
    config: Config, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that stop logs shutdown message."""
    import logging

    caplog.set_level(logging.INFO)
    app = Application(config)
    await app.stop()

    assert "Stopping DVD to Plex application" in caplog.text
    assert "Application stopped" in caplog.text


@pytest.mark.asyncio
async def test_shutdown_event_is_set_on_signal(config: Config) -> None:
    """Test that shutdown event is set when signal handler is called."""
    app = Application(config)

    # Simulate signal handler being called
    app._shutdown_event.clear()
    assert not app._shutdown_event.is_set()

    # Call the handler directly (can't easily send signals in tests)
    app._handle_shutdown_signal()

    assert app._shutdown_event.is_set()
