"""Tests for the drive watcher service."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from dvdtoplex.config import Config
from dvdtoplex.database import Database
from dvdtoplex.drives import DriveStatus
from dvdtoplex.services.drive_watcher import DriveWatcher


class TestDriveWatcher:
    """Tests for DriveWatcher service."""

    @pytest.fixture
    def temp_workspace(self) -> Path:
        """Create a temporary workspace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def config(self, temp_workspace: Path) -> Config:
        """Create a test configuration."""
        return Config(
            pushover_user_key="",
            pushover_api_token="",
            tmdb_api_token="",
            workspace_dir=temp_workspace,
            plex_movies_dir=temp_workspace / "movies",
            plex_tv_dir=temp_workspace / "tv",
            web_host="127.0.0.1",
            web_port=8080,
            drive_poll_interval=0.1,  # Fast polling for tests
        )

    @pytest_asyncio.fixture
    async def database(self, temp_workspace: Path) -> Database:
        """Create a test database."""
        db = Database(temp_workspace / "test.db")
        await db.connect()
        yield db
        await db.close()

    @pytest.fixture
    def drive_watcher(self, config: Config, database: Database) -> DriveWatcher:
        """Create a DriveWatcher instance."""
        return DriveWatcher(config, database, drive_ids=["/dev/disk2"])

    @pytest.mark.asyncio
    async def test_on_disc_inserted_creates_job(
        self, drive_watcher: DriveWatcher, database: Database
    ) -> None:
        """Should create a job when disc is inserted."""
        status = DriveStatus(
            drive_id="/dev/disk2",
            vendor="MATSHITA",
            has_disc=True,
            disc_label="TEST_MOVIE",
        )

        await drive_watcher._on_disc_inserted("/dev/disk2", status)

        jobs = await database.get_pending_jobs()
        assert len(jobs) == 1
        assert jobs[0].drive_id == "/dev/disk2"
        assert jobs[0].disc_label == "TEST_MOVIE"

    @pytest.mark.asyncio
    async def test_on_disc_inserted_skips_if_active_job(
        self, drive_watcher: DriveWatcher, database: Database
    ) -> None:
        """Should not create job if drive already has active job."""
        # Create an existing active job
        await database.create_job("/dev/disk2", "EXISTING_DVD")

        status = DriveStatus(
            drive_id="/dev/disk2",
            vendor="MATSHITA",
            has_disc=True,
            disc_label="NEW_DVD",
        )

        await drive_watcher._on_disc_inserted("/dev/disk2", status)

        # Should still only have one job
        jobs = await database.get_pending_jobs()
        assert len(jobs) == 1
        assert jobs[0].disc_label == "EXISTING_DVD"

    @pytest.mark.asyncio
    async def test_on_disc_inserted_unknown_label(
        self, drive_watcher: DriveWatcher, database: Database
    ) -> None:
        """Should use UNKNOWN_DISC for discs without label."""
        status = DriveStatus(
            drive_id="/dev/disk2",
            vendor="MATSHITA",
            has_disc=True,
            disc_label=None,
        )

        await drive_watcher._on_disc_inserted("/dev/disk2", status)

        jobs = await database.get_pending_jobs()
        assert len(jobs) == 1
        assert jobs[0].disc_label == "UNKNOWN_DISC"

    @pytest.mark.asyncio
    async def test_on_disc_inserted_uses_current_mode(
        self, drive_watcher: DriveWatcher, database: Database
    ) -> None:
        """Should use current mode from settings when creating job."""
        from dvdtoplex.database import RipMode

        # Set the current mode to home_movies
        await database.set_setting("current_mode", "home_movies")

        status = DriveStatus(
            drive_id="/dev/disk2",
            vendor="MATSHITA",
            has_disc=True,
            disc_label="HOME_VIDEO",
        )

        await drive_watcher._on_disc_inserted("/dev/disk2", status)

        jobs = await database.get_pending_jobs()
        assert len(jobs) == 1
        assert jobs[0].rip_mode == RipMode.HOME_MOVIES

    @pytest.mark.asyncio
    async def test_on_disc_inserted_default_mode_is_movie(
        self, drive_watcher: DriveWatcher, database: Database
    ) -> None:
        """Should default to MOVIE mode if no setting."""
        from dvdtoplex.database import RipMode

        status = DriveStatus(
            drive_id="/dev/disk2",
            vendor="MATSHITA",
            has_disc=True,
            disc_label="TEST_DVD",
        )

        await drive_watcher._on_disc_inserted("/dev/disk2", status)

        jobs = await database.get_pending_jobs()
        assert len(jobs) == 1
        assert jobs[0].rip_mode == RipMode.MOVIE

    @pytest.mark.asyncio
    async def test_start_stop(self, drive_watcher: DriveWatcher) -> None:
        """Should start and stop cleanly."""
        with patch("dvdtoplex.services.drive_watcher.get_drive_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = DriveStatus(
                drive_id="/dev/disk2",
                vendor="TEST",
                has_disc=False,
                disc_label=None,
            )

            await drive_watcher.start()
            assert drive_watcher._running is True

            await drive_watcher.stop()
            assert drive_watcher._running is False
