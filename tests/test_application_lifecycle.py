"""Tests for Application lifecycle (US-011).

Verifies the Application can initialize and shutdown cleanly.
"""

import pytest
import pytest_asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from dvdtoplex.config import Config
from dvdtoplex.main import Application


@pytest_asyncio.fixture
async def temp_config() -> Config:
    """Create a Config with a temporary workspace directory."""
    with TemporaryDirectory() as tmpdir:
        config = Config(workspace_dir=Path(tmpdir))
        yield config


@pytest.mark.asyncio
async def test_application_initialize_creates_directories(temp_config: Config) -> None:
    """Test that initialize() creates workspace and staging directories."""
    app = Application(temp_config)

    # Directories should not exist yet
    assert not temp_config.workspace_dir.exists() or not any(temp_config.workspace_dir.iterdir())

    await app.initialize()

    # Verify directories exist
    assert temp_config.workspace_dir.exists(), "workspace_dir should exist"
    assert temp_config.staging_dir.exists(), "staging_dir should exist"
    assert temp_config.encoding_dir.exists(), "encoding_dir should exist"

    # Cleanup
    await app.shutdown()


@pytest.mark.asyncio
async def test_application_initialize_creates_database(temp_config: Config) -> None:
    """Test that initialize() creates and initializes the database."""
    app = Application(temp_config)

    # Database should be closed before initialize
    assert app.database.is_closed, "database should be closed before initialize"

    await app.initialize()

    # Verify database is initialized and open
    assert app.database is not None, "database should be initialized"
    assert not app.database.is_closed, "database should be open after initialize"

    # Cleanup
    await app.shutdown()


@pytest.mark.asyncio
async def test_application_shutdown_closes_database(temp_config: Config) -> None:
    """Test that shutdown() closes the database connection."""
    app = Application(temp_config)
    await app.initialize()

    # Verify database is open
    assert app.database is not None
    assert not app.database.is_closed

    await app.shutdown()

    # After shutdown, database should be closed
    assert app.database.is_closed, "database should be closed after shutdown"


@pytest.mark.asyncio
async def test_application_full_lifecycle(temp_config: Config) -> None:
    """Test complete Application lifecycle: init -> shutdown."""
    app = Application(temp_config)

    # Phase 1: Initialize
    await app.initialize()

    # Verify initialization
    assert temp_config.workspace_dir.exists()
    assert temp_config.staging_dir.exists()
    assert temp_config.encoding_dir.exists()
    assert app.database is not None
    assert not app.database.is_closed

    # Phase 2: Shutdown
    await app.shutdown()

    # Verify shutdown
    assert app.database.is_closed, "database should be closed after shutdown"
    print("Application shutdown OK")


@pytest.mark.asyncio
async def test_application_shutdown_idempotent(temp_config: Config) -> None:
    """Test that calling shutdown multiple times is safe."""
    app = Application(temp_config)
    await app.initialize()

    # First shutdown
    await app.shutdown()
    assert app.database.is_closed, "database should be closed after shutdown"

    # Second shutdown should not raise
    await app.shutdown()
    assert app.database.is_closed, "database should still be closed"


class TestApplicationLifecycleWithRealTempDir:
    """Test Application lifecycle using a real temporary directory context manager."""

    @pytest.mark.asyncio
    async def test_initialize_shutdown_cycle(self) -> None:
        """Test Application can be initialized and shut down cleanly."""
        with TemporaryDirectory() as tmpdir:
            config = Config(workspace_dir=Path(tmpdir))
            app = Application(config)

            # Initialize
            await app.initialize()

            # Verify workspace and staging directories exist
            assert config.workspace_dir.exists()
            assert config.staging_dir.exists()

            # Verify database is initialized (not None)
            assert app.database is not None

            # Shutdown
            await app.shutdown()

            print("Application shutdown OK")
