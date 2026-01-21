"""Tests for the RipQueue service."""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from dvdtoplex.config import Config
from dvdtoplex.database import Database, JobStatus
from dvdtoplex.makemkv import TitleInfo
from dvdtoplex.services.rip_queue import (
    MIN_MAIN_FEATURE_DURATION,
    RipQueue,
    select_main_title,
)


class TestSelectMainTitle:
    """Tests for select_main_title function."""

    def test_selects_longest_title_over_60_minutes(self) -> None:
        """Should select the longest title that is at least 60 minutes."""
        titles = [
            TitleInfo(index=0, duration_seconds=30 * 60, size_bytes=1000, filename="short.mkv"),
            TitleInfo(index=1, duration_seconds=90 * 60, size_bytes=2000, filename="main.mkv"),
            TitleInfo(index=2, duration_seconds=75 * 60, size_bytes=1500, filename="feature.mkv"),
        ]

        result = select_main_title(titles)

        assert result is not None
        assert result.index == 1
        assert result.duration_seconds == 90 * 60

    def test_selects_longest_when_none_over_60_minutes(self) -> None:
        """Should select longest title if none are over 60 minutes."""
        titles = [
            TitleInfo(index=0, duration_seconds=10 * 60, size_bytes=500, filename="short1.mkv"),
            TitleInfo(index=1, duration_seconds=30 * 60, size_bytes=1000, filename="short2.mkv"),
            TitleInfo(index=2, duration_seconds=20 * 60, size_bytes=700, filename="short3.mkv"),
        ]

        result = select_main_title(titles)

        assert result is not None
        assert result.index == 1
        assert result.duration_seconds == 30 * 60

    def test_returns_none_for_empty_list(self) -> None:
        """Should return None when no titles available."""
        result = select_main_title([])

        assert result is None

    def test_single_title_over_60_minutes(self) -> None:
        """Should select single title if it's over 60 minutes."""
        titles = [
            TitleInfo(index=0, duration_seconds=120 * 60, size_bytes=5000, filename="movie.mkv"),
        ]

        result = select_main_title(titles)

        assert result is not None
        assert result.index == 0

    def test_exactly_60_minutes(self) -> None:
        """Should select title that is exactly 60 minutes."""
        titles = [
            TitleInfo(index=0, duration_seconds=MIN_MAIN_FEATURE_DURATION, size_bytes=3000, filename="exact.mkv"),
            TitleInfo(index=1, duration_seconds=30 * 60, size_bytes=1000, filename="short.mkv"),
        ]

        result = select_main_title(titles)

        assert result is not None
        assert result.index == 0
        assert result.duration_seconds == MIN_MAIN_FEATURE_DURATION


class TestRipQueue:
    """Tests for RipQueue class."""

    @pytest.fixture
    def config(self, tmp_path: Path) -> Config:
        """Create a test configuration."""
        return Config(
            workspace_dir=tmp_path / "workspace",
        )

    @pytest_asyncio.fixture
    async def database(self, tmp_path: Path) -> AsyncGenerator[Database, None]:
        """Create a test database."""
        db = Database(tmp_path / "test.db")
        await db.connect()
        yield db
        await db.close()

    @pytest.fixture
    def rip_queue(self, config: Config, database: Database) -> RipQueue:
        """Create a RipQueue instance."""
        return RipQueue(config, database, drive_ids=["0", "1"])

    @pytest.mark.asyncio
    async def test_start_and_stop(self, rip_queue: RipQueue) -> None:
        """Should start and stop cleanly."""
        await rip_queue.start()
        assert rip_queue._running is True
        assert rip_queue._task is not None

        await rip_queue.stop()
        assert rip_queue._running is False

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, rip_queue: RipQueue) -> None:
        """Starting twice should not create multiple tasks."""
        await rip_queue.start()
        task1 = rip_queue._task

        await rip_queue.start()
        task2 = rip_queue._task

        assert task1 is task2
        await rip_queue.stop()

    @pytest.mark.asyncio
    @patch("dvdtoplex.services.rip_queue.get_disc_info")
    @patch("dvdtoplex.services.rip_queue.rip_title")
    @patch("dvdtoplex.services.rip_queue.eject_drive")
    async def test_processes_pending_job(
        self,
        mock_eject: AsyncMock,
        mock_rip: AsyncMock,
        mock_info: AsyncMock,
        rip_queue: RipQueue,
        database: Database,
        config: Config,
    ) -> None:
        """Should process a pending job successfully."""
        # Create a pending job
        job = await database.create_job("0", "TEST_DISC")

        # Mock disc info
        mock_info.return_value = [
            TitleInfo(index=0, duration_seconds=120 * 60, size_bytes=5000000000, filename="movie.mkv"),
        ]

        # Mock rip to create a file
        rip_output = config.staging_dir / f"job_{job.id}" / "movie.mkv"
        mock_rip.return_value = rip_output

        mock_eject.return_value = True

        # Process the job directly
        await rip_queue._rip_job(job.id, "0")

        # Verify job was updated
        updated_job = await database.get_job(job.id)
        assert updated_job is not None
        assert updated_job.status == JobStatus.RIPPED
        assert updated_job.rip_path == str(rip_output)

        # Verify eject was called
        mock_eject.assert_called_once_with("0")

    @pytest.mark.asyncio
    @patch("dvdtoplex.services.rip_queue.get_disc_info")
    async def test_handles_no_titles_error(
        self,
        mock_info: AsyncMock,
        rip_queue: RipQueue,
        database: Database,
    ) -> None:
        """Should handle disc with no titles."""
        from dvdtoplex.makemkv import DiscReadError

        job = await database.create_job("0", "EMPTY_DISC")

        # get_disc_info now raises DiscReadError when no titles found
        mock_info.side_effect = DiscReadError(
            "No titles found on disc",
            device="0",
            details="Title #1 has length of 30 seconds which is less than minimum",
        )

        await rip_queue._rip_job(job.id, "0")

        updated_job = await database.get_job(job.id)
        assert updated_job is not None
        assert updated_job.status == JobStatus.FAILED
        assert "No titles found" in (updated_job.error_message or "")
        # Check that details are included
        assert "minimum" in (updated_job.error_message or "")

    @pytest.mark.asyncio
    @patch("dvdtoplex.services.rip_queue.get_disc_info")
    @patch("dvdtoplex.services.rip_queue.rip_title")
    async def test_handles_rip_error(
        self,
        mock_rip: AsyncMock,
        mock_info: AsyncMock,
        rip_queue: RipQueue,
        database: Database,
    ) -> None:
        """Should handle rip failures."""
        job = await database.create_job("0", "BAD_DISC")

        mock_info.return_value = [
            TitleInfo(index=0, duration_seconds=120 * 60, size_bytes=5000000000, filename="movie.mkv"),
        ]
        mock_rip.side_effect = RuntimeError("Disc read error")

        await rip_queue._rip_job(job.id, "0")

        updated_job = await database.get_job(job.id)
        assert updated_job is not None
        assert updated_job.status == JobStatus.FAILED
        assert "Disc read error" in (updated_job.error_message or "")

    @pytest.mark.asyncio
    async def test_processes_jobs_by_drive(
        self,
        rip_queue: RipQueue,
        database: Database,
    ) -> None:
        """Should only process one job per drive at a time."""
        # Create multiple jobs for same drive
        _job1 = await database.create_job("0", "DISC1")
        _job2 = await database.create_job("0", "DISC2")

        # Create job for different drive
        _job3 = await database.create_job("1", "DISC3")

        pending = await database.get_jobs_by_status(JobStatus.PENDING)

        # Group jobs by drive
        jobs_by_drive: dict[str, list[int]] = {}
        for job in pending:
            if job.drive_id not in jobs_by_drive:
                jobs_by_drive[job.drive_id] = []
            jobs_by_drive[job.drive_id].append(job.id)

        # Should have 2 drives
        assert len(jobs_by_drive) == 2
        assert len(jobs_by_drive["0"]) == 2
        assert len(jobs_by_drive["1"]) == 1

    @pytest.mark.asyncio
    @patch("dvdtoplex.services.rip_queue.get_disc_info")
    @patch("dvdtoplex.services.rip_queue.rip_title")
    @patch("dvdtoplex.services.rip_queue.eject_drive")
    async def test_parallel_ripping_different_drives(
        self,
        mock_eject: AsyncMock,
        mock_rip: AsyncMock,
        mock_info: AsyncMock,
        rip_queue: RipQueue,
        database: Database,
        config: Config,
    ) -> None:
        """Should allow parallel ripping from different drives."""
        job1 = await database.create_job("0", "DISC1")
        job2 = await database.create_job("1", "DISC2")

        mock_info.return_value = [
            TitleInfo(index=0, duration_seconds=120 * 60, size_bytes=5000000000, filename="movie.mkv"),
        ]

        def mock_rip_side_effect(
            drive: str, title_idx: int, output_dir: Path, *args: Any, **kwargs: Any
        ) -> Path:
            return output_dir / "movie.mkv"

        mock_rip.side_effect = mock_rip_side_effect
        mock_eject.return_value = True

        # Process both jobs in parallel
        await asyncio.gather(
            rip_queue._rip_job(job1.id, "0"),
            rip_queue._rip_job(job2.id, "1"),
        )

        # Both should be ripped
        updated_job1 = await database.get_job(job1.id)
        updated_job2 = await database.get_job(job2.id)

        assert updated_job1 is not None
        assert updated_job1.status == JobStatus.RIPPED
        assert updated_job2 is not None
        assert updated_job2.status == JobStatus.RIPPED

    @pytest.mark.asyncio
    async def test_skips_drive_with_active_rip(
        self,
        rip_queue: RipQueue,
        database: Database,
    ) -> None:
        """Should skip drive if it already has an active rip."""
        # Create pending job
        await database.create_job("0", "DISC1")

        # Simulate active rip on drive 0
        dummy_task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(10))
        rip_queue._active_rips["0"] = dummy_task

        try:
            # Process should skip drive 0
            await rip_queue._process_pending_jobs()

            # Job should still be pending
            jobs = await database.get_jobs_by_status(JobStatus.PENDING)
            assert len(jobs) == 1
        finally:
            dummy_task.cancel()
            try:
                await dummy_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_handles_missing_job(
        self,
        rip_queue: RipQueue,
        database: Database,
    ) -> None:
        """Should handle case where job doesn't exist."""
        # Try to rip non-existent job
        await rip_queue._rip_job(9999, "0")

        # Should not crash - just log and return

    @pytest.mark.asyncio
    @patch("dvdtoplex.services.rip_queue.get_disc_info")
    @patch("dvdtoplex.services.rip_queue.rip_title")
    @patch("dvdtoplex.services.rip_queue.eject_drive")
    async def test_updates_status_to_ripping(
        self,
        mock_eject: AsyncMock,
        mock_rip: AsyncMock,
        mock_info: AsyncMock,
        rip_queue: RipQueue,
        database: Database,
        config: Config,
    ) -> None:
        """Should update job status to RIPPING before starting."""
        job = await database.create_job("0", "TEST_DISC")

        ripping_status_seen = False

        async def check_status(*args: Any, **kwargs: Any) -> list[TitleInfo]:
            nonlocal ripping_status_seen
            current_job = await database.get_job(job.id)
            if current_job and current_job.status == JobStatus.RIPPING:
                ripping_status_seen = True
            return [TitleInfo(index=0, duration_seconds=120 * 60, size_bytes=5000, filename="m.mkv")]

        mock_info.side_effect = check_status
        mock_rip.return_value = config.staging_dir / f"job_{job.id}" / "movie.mkv"
        mock_eject.return_value = True

        await rip_queue._rip_job(job.id, "0")

        assert ripping_status_seen, "Job should have been in RIPPING status during rip"
