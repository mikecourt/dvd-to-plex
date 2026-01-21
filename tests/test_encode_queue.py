"""Tests for the encode queue service."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio

from dvdtoplex.config import Config
from dvdtoplex.database import Database, JobStatus
from dvdtoplex.services.encode_queue import EncodeQueue


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "staging").mkdir()
    (workspace / "encoding").mkdir()
    return workspace


@pytest.fixture
def config(temp_workspace: Path) -> Config:
    """Create a test configuration."""
    return Config(
        pushover_user_key="test_user",
        pushover_api_token="test_token",
        tmdb_api_token="test_tmdb",
        workspace_dir=temp_workspace,
        plex_movies_dir=temp_workspace / "plex_movies",
        plex_tv_dir=temp_workspace / "plex_tv",
        web_host="127.0.0.1",
        web_port=8080,
    )


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> Database:
    """Create and initialize a test database."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    yield db
    await db.close()


class TestEncodeQueue:
    """Tests for the EncodeQueue class."""

    @pytest.mark.asyncio
    async def test_start_stop(self, config: Config, database: Database) -> None:
        """Test starting and stopping the encode queue."""
        queue = EncodeQueue(config, database)

        await queue.start()
        assert queue._running is True
        assert queue._task is not None

        await queue.stop()
        assert queue._running is False
        assert queue._task is None

    @pytest.mark.asyncio
    async def test_start_twice_is_idempotent(
        self, config: Config, database: Database
    ) -> None:
        """Test that starting the queue twice doesn't create duplicate tasks."""
        queue = EncodeQueue(config, database)

        await queue.start()
        task1 = queue._task

        await queue.start()
        task2 = queue._task

        assert task1 is task2

        await queue.stop()

    @pytest.mark.asyncio
    async def test_process_job_no_rip_path(
        self, config: Config, database: Database
    ) -> None:
        """Test handling of a job with no rip_path."""
        queue = EncodeQueue(config, database)

        # Create a job without a rip_path
        created_job = await database.create_job("drive0", "TEST_DISC")
        await database.update_job_status(created_job.id, JobStatus.RIPPED)

        await queue._process_next_job()

        job = await database.get_job(created_job.id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert "No rip path found" in job.error_message

    @pytest.mark.asyncio
    async def test_process_job_missing_rip_file(
        self, config: Config, database: Database, temp_workspace: Path
    ) -> None:
        """Test handling of a job with a non-existent rip file."""
        queue = EncodeQueue(config, database)

        # Create a job with a rip_path that doesn't exist
        created_job = await database.create_job("drive0", "TEST_DISC")
        fake_rip_path = temp_workspace / "staging" / "nonexistent.mkv"
        await database.update_job_status(
            created_job.id, JobStatus.RIPPED, rip_path=str(fake_rip_path)
        )

        await queue._process_next_job()

        job = await database.get_job(created_job.id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert "not found" in job.error_message

    @pytest.mark.asyncio
    async def test_process_job_encode_success(
        self, config: Config, database: Database, temp_workspace: Path
    ) -> None:
        """Test successful encoding of a job."""
        queue = EncodeQueue(config, database)

        # Create a job with a real rip file
        rip_dir = temp_workspace / "staging" / "job_1"
        rip_dir.mkdir(parents=True)
        rip_file = rip_dir / "movie.mkv"
        rip_file.write_text("fake video content")

        created_job = await database.create_job("drive0", "TEST_DISC")
        await database.update_job_status(
            created_job.id, JobStatus.RIPPED, rip_path=str(rip_file)
        )

        with patch("dvdtoplex.services.encode_queue.encode_file") as mock_encode:
            mock_encode.return_value = True

            await queue._process_next_job()

            mock_encode.assert_called_once()
            call_args = mock_encode.call_args
            # encode_file is called with (input_path, output_path, progress_callback)
            assert call_args[0][0] == rip_file

        job = await database.get_job(created_job.id)
        assert job is not None
        assert job.status == JobStatus.ENCODED
        assert job.encode_path is not None

    @pytest.mark.asyncio
    async def test_process_job_encode_failure(
        self, config: Config, database: Database, temp_workspace: Path
    ) -> None:
        """Test handling of an encoding failure."""
        from dvdtoplex.handbrake import EncodeError

        queue = EncodeQueue(config, database)

        # Create a job with a real rip file
        rip_dir = temp_workspace / "staging" / "job_1"
        rip_dir.mkdir(parents=True)
        rip_file = rip_dir / "movie.mkv"
        rip_file.write_text("fake video content")

        created_job = await database.create_job("drive0", "TEST_DISC")
        await database.update_job_status(
            created_job.id, JobStatus.RIPPED, rip_path=str(rip_file)
        )

        with patch("dvdtoplex.services.encode_queue.encode_file") as mock_encode:
            mock_encode.side_effect = EncodeError(
                "Encoding failed",
                exit_code=1,
                input_path=rip_file,
                output_path=rip_file.parent / "output.mkv",
            )

            await queue._process_next_job()

            mock_encode.assert_called_once()

        job = await database.get_job(created_job.id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert "Encoding failed" in str(job.error_message)

    @pytest.mark.asyncio
    async def test_process_job_encode_exception(
        self, config: Config, database: Database, temp_workspace: Path
    ) -> None:
        """Test handling of an exception during encoding."""
        queue = EncodeQueue(config, database)

        # Create a job with a real rip file
        rip_dir = temp_workspace / "staging" / "job_1"
        rip_dir.mkdir(parents=True)
        rip_file = rip_dir / "movie.mkv"
        rip_file.write_text("fake video content")

        created_job = await database.create_job("drive0", "TEST_DISC")
        await database.update_job_status(
            created_job.id, JobStatus.RIPPED, rip_path=str(rip_file)
        )

        with patch("dvdtoplex.services.encode_queue.encode_file") as mock_encode:
            mock_encode.side_effect = RuntimeError("HandBrake crashed")

            await queue._process_next_job()

        job = await database.get_job(created_job.id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert "HandBrake crashed" in job.error_message

    @pytest.mark.asyncio
    async def test_no_jobs_to_process(self, config: Config, database: Database) -> None:
        """Test that nothing happens when there are no jobs to process."""
        queue = EncodeQueue(config, database)

        # No jobs in the database
        await queue._process_next_job()

        # Should complete without error
        jobs = await database.get_jobs_by_status(JobStatus.RIPPED)
        assert len(jobs) == 0

    @pytest.mark.asyncio
    async def test_jobs_processed_in_order(
        self, config: Config, database: Database, temp_workspace: Path
    ) -> None:
        """Test that jobs are processed in the order they were created."""
        queue = EncodeQueue(config, database)

        # Create multiple jobs
        created_jobs = []
        for i in range(3):
            rip_dir = temp_workspace / "staging" / f"job_{i}"
            rip_dir.mkdir(parents=True)
            rip_file = rip_dir / "movie.mkv"
            rip_file.write_text(f"fake video content {i}")

            created_job = await database.create_job(f"drive{i}", f"DISC_{i}")
            await database.update_job_status(
                created_job.id, JobStatus.RIPPED, rip_path=str(rip_file)
            )
            created_jobs.append(created_job)

        processed_order: list[int] = []

        with patch("dvdtoplex.services.encode_queue.encode_file") as mock_encode:
            mock_encode.return_value = True

            for _ in range(3):
                # Get the next job that will be processed
                jobs = await database.get_jobs_by_status(JobStatus.RIPPED)
                if jobs:
                    processed_order.append(jobs[0].id)
                await queue._process_next_job()

        # Jobs should be processed in FIFO order
        assert processed_order == [j.id for j in created_jobs]

    @pytest.mark.asyncio
    async def test_encoding_status_transition(
        self, config: Config, database: Database, temp_workspace: Path
    ) -> None:
        """Test that job status transitions correctly during encoding."""
        queue = EncodeQueue(config, database)

        rip_dir = temp_workspace / "staging" / "job_1"
        rip_dir.mkdir(parents=True)
        rip_file = rip_dir / "movie.mkv"
        rip_file.write_text("fake video content")

        created_job = await database.create_job("drive0", "TEST_DISC")
        await database.update_job_status(
            created_job.id, JobStatus.RIPPED, rip_path=str(rip_file)
        )

        status_during_encode: list[JobStatus] = []

        async def mock_encode_with_status_check(*args: Any, **kwargs: Any) -> bool:
            job = await database.get_job(created_job.id)
            assert job is not None
            status_during_encode.append(job.status)
            return True

        with patch(
            "dvdtoplex.services.encode_queue.encode_file",
            side_effect=mock_encode_with_status_check,
        ):
            await queue._process_next_job()

        # Status should be ENCODING during the encode
        assert status_during_encode == [JobStatus.ENCODING]

        # Final status should be ENCODED
        job = await database.get_job(created_job.id)
        assert job is not None
        assert job.status == JobStatus.ENCODED
