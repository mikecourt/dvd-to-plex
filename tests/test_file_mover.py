"""Tests for the FileMover service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from dvdtoplex.services.file_mover import (
    FileMover,
    format_movie_filename,
    format_movie_folder,
    sanitize_filename,
)


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_removes_invalid_chars(self) -> None:
        """Should remove characters invalid on common filesystems."""
        assert sanitize_filename('Movie: The "Sequel"') == "Movie The Sequel"
        assert sanitize_filename("What/If?") == "WhatIf"
        assert sanitize_filename("File<>Name") == "FileName"
        assert sanitize_filename("Path\\To\\File") == "PathToFile"
        assert sanitize_filename("Pipe|Line") == "PipeLine"
        assert sanitize_filename("Star*Wars") == "StarWars"

    def test_preserves_valid_chars(self) -> None:
        """Should preserve valid filename characters."""
        assert sanitize_filename("Movie Name (2024)") == "Movie Name (2024)"
        assert sanitize_filename("The Movie - Part 1") == "The Movie - Part 1"
        assert sanitize_filename("Film's Title") == "Film's Title"

    def test_collapses_multiple_spaces(self) -> None:
        """Should collapse multiple spaces into single space."""
        assert sanitize_filename("Movie    Name") == "Movie Name"
        assert sanitize_filename("  Spaced   Out  ") == "Spaced Out"

    def test_strips_leading_trailing_whitespace_and_dots(self) -> None:
        """Should strip leading/trailing whitespace and dots."""
        assert sanitize_filename("  Movie Name  ") == "Movie Name"
        assert sanitize_filename("...Movie Name...") == "Movie Name"
        assert sanitize_filename(" . Movie . ") == "Movie"

    def test_empty_string(self) -> None:
        """Should handle empty strings."""
        assert sanitize_filename("") == ""
        assert sanitize_filename("   ") == ""

    def test_control_characters(self) -> None:
        """Should remove control characters."""
        assert sanitize_filename("Movie\x00Name") == "MovieName"
        assert sanitize_filename("Test\x1fFile") == "TestFile"


class TestFormatMovieFilename:
    """Tests for format_movie_filename function."""

    def test_with_year(self) -> None:
        """Should format as 'Title (Year).mkv'."""
        assert format_movie_filename("Inception", 2010) == "Inception (2010).mkv"
        assert format_movie_filename("The Matrix", 1999) == "The Matrix (1999).mkv"

    def test_without_year(self) -> None:
        """Should format as 'Title.mkv' when year is None."""
        assert format_movie_filename("Unknown Movie", None) == "Unknown Movie.mkv"

    def test_sanitizes_title(self) -> None:
        """Should sanitize the title."""
        assert (
            format_movie_filename('Movie: The "Sequel"', 2024)
            == "Movie The Sequel (2024).mkv"
        )

    def test_year_zero(self) -> None:
        """Should include year even if zero."""
        assert format_movie_filename("Movie", 0) == "Movie.mkv"


class TestFormatMovieFolder:
    """Tests for format_movie_folder function."""

    def test_with_year(self) -> None:
        """Should format as 'Title (Year)'."""
        assert format_movie_folder("Inception", 2010) == "Inception (2010)"
        assert format_movie_folder("The Matrix", 1999) == "The Matrix (1999)"

    def test_without_year(self) -> None:
        """Should format as 'Title' when year is None."""
        assert format_movie_folder("Unknown Movie", None) == "Unknown Movie"

    def test_sanitizes_title(self) -> None:
        """Should sanitize the title."""
        assert format_movie_folder('Movie: The "Sequel"', 2024) == "Movie The Sequel (2024)"


@dataclass
class MockConfig:
    """Mock configuration for testing."""

    plex_movies_dir: Path
    plex_tv_dir: Path
    plex_home_movies_dir: Path = None
    plex_other_dir: Path = None

    def __post_init__(self):
        if self.plex_home_movies_dir is None:
            self.plex_home_movies_dir = self.plex_movies_dir.parent / "plex_home_movies"
        if self.plex_other_dir is None:
            self.plex_other_dir = self.plex_movies_dir.parent / "plex_other"


@dataclass
class MockDatabase:
    """Mock database for testing."""

    jobs: list[dict[str, Any]] = field(default_factory=list)
    updated_jobs: list[dict[str, Any]] = field(default_factory=list)
    collection: list[dict[str, Any]] = field(default_factory=list)

    async def get_jobs_by_status(self, status: str) -> list[dict[str, Any]]:
        """Return jobs matching the given status."""
        return [j for j in self.jobs if j.get("status") == status]

    async def update_job(self, job_id: int, **kwargs: Any) -> None:
        """Record job update."""
        self.updated_jobs.append({"id": job_id, **kwargs})
        # Update the job in the jobs list
        for job in self.jobs:
            if job["id"] == job_id:
                job.update(kwargs)
                break

    async def add_to_collection(
        self,
        title: str,
        year: int | None,
        content_type: str,
        tmdb_id: int | None,
        final_path: str,
    ) -> None:
        """Record collection addition."""
        self.collection.append(
            {
                "title": title,
                "year": year,
                "content_type": content_type,
                "tmdb_id": tmdb_id,
                "final_path": final_path,
            }
        )


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with necessary directories."""
    plex_movies = tmp_path / "plex_movies"
    plex_tv = tmp_path / "plex_tv"
    staging = tmp_path / "staging"
    encoding = tmp_path / "encoding"

    plex_movies.mkdir()
    plex_tv.mkdir()
    staging.mkdir()
    encoding.mkdir()

    return tmp_path


@pytest.fixture
def config(temp_workspace: Path) -> MockConfig:
    """Create a mock configuration."""
    return MockConfig(
        plex_movies_dir=temp_workspace / "plex_movies",
        plex_tv_dir=temp_workspace / "plex_tv",
    )


@pytest.fixture
def database() -> MockDatabase:
    """Create a mock database."""
    return MockDatabase()


class TestFileMoverInit:
    """Tests for FileMover initialization."""

    def test_init(self, config: MockConfig, database: MockDatabase) -> None:
        """Should initialize with config and database."""
        mover = FileMover(config, database)
        assert mover.config is config
        assert mover.database is database
        assert not mover._running
        assert mover._task is None


class TestFileMoverStartStop:
    """Tests for FileMover start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running_and_creates_task(
        self, config: MockConfig, database: MockDatabase
    ) -> None:
        """Should set running flag and create background task."""
        mover = FileMover(config, database)
        await mover.start()

        assert mover._running
        assert mover._task is not None
        assert not mover._task.done()

        await mover.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(
        self, config: MockConfig, database: MockDatabase
    ) -> None:
        """Should not create multiple tasks if already running."""
        mover = FileMover(config, database)
        await mover.start()
        first_task = mover._task

        await mover.start()
        assert mover._task is first_task

        await mover.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(
        self, config: MockConfig, database: MockDatabase
    ) -> None:
        """Should cancel task and reset state."""
        mover = FileMover(config, database)
        await mover.start()
        await mover.stop()

        assert not mover._running
        assert mover._task is None


class TestFileMoverMoveMovie:
    """Tests for movie file moving to Plex directory in Title (Year) folder."""

    @pytest.mark.asyncio
    async def test_moves_movie_to_title_year_folder(
        self, config: MockConfig, database: MockDatabase, temp_workspace: Path
    ) -> None:
        """Should move movie to Plex movies dir in Title (Year) folder."""
        # Create a fake encoded file
        encode_dir = temp_workspace / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("fake movie content")

        # Set up the job
        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Inception",
                "identified_year": 2010,
                "tmdb_id": 27205,
                "rip_path": None,
                "status": "moving",
            }
        )

        mover = FileMover(config, database)
        await mover._process_jobs()

        # Check file was moved to correct location: Title (Year)/Title (Year).mkv
        expected_path = config.plex_movies_dir / "Inception (2010)" / "Inception (2010).mkv"
        assert expected_path.exists(), f"Expected movie at {expected_path}"
        assert expected_path.read_text() == "fake movie content"

        # Check job was updated
        assert len(database.updated_jobs) == 1
        assert database.updated_jobs[0]["status"] == "complete"
        assert database.updated_jobs[0]["final_path"] == str(expected_path)

        # Check collection was updated
        assert len(database.collection) == 1
        assert database.collection[0]["title"] == "Inception"
        assert database.collection[0]["year"] == 2010

    @pytest.mark.asyncio
    async def test_movie_folder_structure(
        self, config: MockConfig, temp_workspace: Path
    ) -> None:
        """Should create proper folder structure: plex_movies/Title (Year)/Title (Year).mkv."""
        # Create a fake encoded file
        encode_file = temp_workspace / "source.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, MockDatabase())
        result = await mover.move_movie(encode_file, "The Matrix", 1999)

        assert result.success
        assert result.final_path is not None

        # Verify folder structure
        expected_folder = config.plex_movies_dir / "The Matrix (1999)"
        expected_file = expected_folder / "The Matrix (1999).mkv"

        assert expected_folder.is_dir(), "Movie folder should exist"
        assert expected_file.exists(), "Movie file should exist in folder"
        assert result.final_path == expected_file

    @pytest.mark.asyncio
    async def test_movie_without_year_uses_title_only(
        self, config: MockConfig, database: MockDatabase, temp_workspace: Path
    ) -> None:
        """Should handle movie without year, using just Title for folder."""
        encode_dir = temp_workspace / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Unknown Movie",
                "identified_year": None,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
            }
        )

        mover = FileMover(config, database)
        await mover._process_jobs()

        # Should be in folder named just "Unknown Movie"
        expected_path = config.plex_movies_dir / "Unknown Movie" / "Unknown Movie.mkv"
        assert expected_path.exists()

    @pytest.mark.asyncio
    async def test_sanitizes_movie_folder_name(
        self, config: MockConfig, temp_workspace: Path
    ) -> None:
        """Should sanitize invalid characters from folder name."""
        encode_file = temp_workspace / "source.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, MockDatabase())
        result = await mover.move_movie(encode_file, 'Movie: The "Sequel"', 2024)

        assert result.success
        # Invalid chars removed, folder should be "Movie The Sequel (2024)"
        expected_folder = config.plex_movies_dir / "Movie The Sequel (2024)"
        assert expected_folder.is_dir()

    @pytest.mark.asyncio
    async def test_move_movie_direct_call(
        self, config: MockConfig, temp_workspace: Path
    ) -> None:
        """Test move_movie method directly."""
        encode_file = temp_workspace / "test_movie.mkv"
        encode_file.write_text("movie data")

        mover = FileMover(config, MockDatabase())
        result = await mover.move_movie(encode_file, "Test Movie", 2023)

        assert result.success
        assert result.final_path == config.plex_movies_dir / "Test Movie (2023)" / "Test Movie (2023).mkv"
        assert result.final_path.exists()
        assert result.final_path.read_text() == "movie data"
        # Source should be gone (moved, not copied)
        assert not encode_file.exists()


class TestFileMoverErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_missing_encode_file(
        self, config: MockConfig, database: MockDatabase
    ) -> None:
        """Should fail job if encoded file doesn't exist."""
        database.jobs.append(
            {
                "id": 1,
                "encode_path": "/nonexistent/file.mkv",
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
            }
        )

        mover = FileMover(config, database)
        await mover._process_jobs()

        assert database.updated_jobs[0]["status"] == "failed"
        assert "not found" in database.updated_jobs[0]["error_message"]

    @pytest.mark.asyncio
    async def test_missing_title(
        self, config: MockConfig, database: MockDatabase, temp_workspace: Path
    ) -> None:
        """Should fail job if title is missing."""
        encode_dir = temp_workspace / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": None,
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
            }
        )

        mover = FileMover(config, database)
        await mover._process_jobs()

        assert database.updated_jobs[0]["status"] == "failed"
        assert "identified_title" in database.updated_jobs[0]["error_message"]

    @pytest.mark.asyncio
    async def test_missing_plex_directory(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should fail gracefully if Plex directory doesn't exist."""
        # Config points to non-existent directory
        config = MockConfig(
            plex_movies_dir=tmp_path / "nonexistent",
            plex_tv_dir=tmp_path / "nonexistent_tv",
        )

        encode_file = tmp_path / "movie.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, database)
        result = await mover.move_movie(encode_file, "Movie", 2024)

        assert not result.success
        assert result.error is not None
        assert "not found" in result.error


class TestFileMoverCleanup:
    """Tests for cleanup after successful move."""

    @pytest.mark.asyncio
    async def test_cleanup_failure_logs_at_error_level(
        self, config: MockConfig, database: MockDatabase, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log cleanup failures at ERROR level for visibility."""
        import logging
        from unittest.mock import patch, AsyncMock

        # Create encode directory with file
        encode_dir = tmp_path / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, database)

        # Patch asyncio.to_thread to simulate rmtree failure
        async def failing_to_thread(func, *args, **kwargs):
            if func.__name__ == "rmtree" or "rmtree" in str(func):
                raise OSError("Permission denied")
            return func(*args, **kwargs)

        with patch("dvdtoplex.services.file_mover.asyncio.to_thread", side_effect=failing_to_thread):
            with caplog.at_level(logging.DEBUG, logger="dvdtoplex.services.file_mover"):
                await mover._cleanup(encode_file, None)

        # Verify ERROR level log was produced for cleanup failure
        error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
        cleanup_errors = [r for r in error_logs if "clean up" in r.message.lower()]
        assert len(cleanup_errors) > 0, f"Expected ERROR log for cleanup failure. Records: {[(r.levelname, r.message) for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_cleans_up_encode_directory(
        self, config: MockConfig, database: MockDatabase, temp_workspace: Path
    ) -> None:
        """Should remove encode directory after successful move."""
        encode_dir = temp_workspace / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
            }
        )

        mover = FileMover(config, database)
        await mover._process_jobs()

        assert not encode_dir.exists()

    @pytest.mark.asyncio
    async def test_cleans_up_rip_directory(
        self, config: MockConfig, database: MockDatabase, temp_workspace: Path
    ) -> None:
        """Should remove rip directory after successful move."""
        encode_dir = temp_workspace / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        rip_dir = temp_workspace / "staging" / "job_1"
        rip_dir.mkdir(parents=True)
        (rip_dir / "ripped_file.mkv").write_text("ripped content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": str(rip_dir),
                "status": "moving",
            }
        )

        mover = FileMover(config, database)
        await mover._process_jobs()

        assert not rip_dir.exists()


class TestFileMoverAddToCollection:
    """Tests for collection tracking after successful move."""

    @pytest.mark.asyncio
    async def test_adds_movie_to_collection(
        self, config: MockConfig, database: MockDatabase, temp_workspace: Path
    ) -> None:
        """Should add movie to collection on successful move."""
        encode_dir = temp_workspace / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Test Movie",
                "identified_year": 2020,
                "tmdb_id": 12345,
                "rip_path": None,
                "status": "moving",
            }
        )

        mover = FileMover(config, database)
        await mover._process_jobs()

        assert len(database.collection) == 1
        assert database.collection[0]["title"] == "Test Movie"
        assert database.collection[0]["year"] == 2020
        assert database.collection[0]["content_type"] == "movie"
        assert database.collection[0]["tmdb_id"] == 12345
        assert "Test Movie (2020)" in database.collection[0]["final_path"]


class TestFileMoverRetry:
    """Tests for retry behavior when Plex directory is missing."""

    @pytest.mark.asyncio
    async def test_missing_plex_directory_returns_retryable_error(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should return retryable=True when Plex directory doesn't exist."""
        config = MockConfig(
            plex_movies_dir=tmp_path / "nonexistent",
            plex_tv_dir=tmp_path / "nonexistent_tv",
        )

        encode_file = tmp_path / "movie.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, database)
        result = await mover.move_movie(encode_file, "Movie", 2024)

        assert not result.success
        assert result.retryable is True
        assert result.error is not None
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_missing_plex_tv_directory_returns_retryable_error(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should return retryable=True when Plex TV directory doesn't exist."""
        config = MockConfig(
            plex_movies_dir=tmp_path / "movies",
            plex_tv_dir=tmp_path / "nonexistent_tv",
        )

        encode_file = tmp_path / "episode.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, database)
        result = await mover._move_tv_episode(encode_file, "Show", 1, 1, "Episode")

        assert not result.success
        assert result.retryable is True
        assert result.error is not None
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_increments_retry_count_on_missing_directory(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should increment retry count and keep job in MOVING status."""
        config = MockConfig(
            plex_movies_dir=tmp_path / "nonexistent",
            plex_tv_dir=tmp_path / "nonexistent_tv",
        )

        encode_dir = tmp_path / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
                "move_retry_count": 0,
            }
        )

        mover = FileMover(config, database, max_retries=3)
        await mover._process_jobs()

        # Job should stay in moving status (not failed)
        assert "status" not in database.updated_jobs[0]
        # Retry count should be incremented
        assert database.updated_jobs[0]["move_retry_count"] == 1
        # Error message should indicate retry
        assert "Retry 1/3" in database.updated_jobs[0]["error_message"]

    @pytest.mark.asyncio
    async def test_continues_retrying_until_max(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should continue incrementing retry count on subsequent failures."""
        config = MockConfig(
            plex_movies_dir=tmp_path / "nonexistent",
            plex_tv_dir=tmp_path / "nonexistent_tv",
        )

        encode_dir = tmp_path / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
                "move_retry_count": 2,  # Already retried twice
            }
        )

        mover = FileMover(config, database, max_retries=3)
        await mover._process_jobs()

        # Job still in moving status with retry count incremented to 3
        assert "status" not in database.updated_jobs[0]
        assert database.updated_jobs[0]["move_retry_count"] == 3
        assert "Retry 3/3" in database.updated_jobs[0]["error_message"]

    @pytest.mark.asyncio
    async def test_fails_after_max_retries_exceeded(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should fail job after max retries exceeded."""
        config = MockConfig(
            plex_movies_dir=tmp_path / "nonexistent",
            plex_tv_dir=tmp_path / "nonexistent_tv",
        )

        encode_dir = tmp_path / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
                "move_retry_count": 3,  # Already at max
            }
        )

        mover = FileMover(config, database, max_retries=3)
        await mover._process_jobs()

        # Job should now be failed
        assert database.updated_jobs[0]["status"] == "failed"
        assert "Max retries exceeded" in database.updated_jobs[0]["error_message"]

    @pytest.mark.asyncio
    async def test_succeeds_on_retry_when_directory_appears(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should succeed when Plex directory exists on retry."""
        # Create Plex directory (simulating drive mount)
        plex_movies = tmp_path / "plex_movies"
        plex_movies.mkdir()

        config = MockConfig(
            plex_movies_dir=plex_movies,
            plex_tv_dir=tmp_path / "plex_tv",
        )

        encode_dir = tmp_path / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
                "move_retry_count": 2,  # Previously failed twice
            }
        )

        mover = FileMover(config, database, max_retries=3)
        await mover._process_jobs()

        # Job should complete successfully
        assert database.updated_jobs[0]["status"] == "complete"
        assert "Movie (2024)" in database.updated_jobs[0]["final_path"]

    @pytest.mark.asyncio
    async def test_handles_null_retry_count(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should handle jobs with null/missing move_retry_count."""
        config = MockConfig(
            plex_movies_dir=tmp_path / "nonexistent",
            plex_tv_dir=tmp_path / "nonexistent_tv",
        )

        encode_dir = tmp_path / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        # Job without move_retry_count field
        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
                # No move_retry_count field
            }
        )

        mover = FileMover(config, database, max_retries=3)
        await mover._process_jobs()

        # Should start from 0 and increment to 1
        assert database.updated_jobs[0]["move_retry_count"] == 1

    @pytest.mark.asyncio
    async def test_custom_max_retries(
        self, database: MockDatabase, tmp_path: Path
    ) -> None:
        """Should respect custom max_retries setting."""
        config = MockConfig(
            plex_movies_dir=tmp_path / "nonexistent",
            plex_tv_dir=tmp_path / "nonexistent_tv",
        )

        encode_dir = tmp_path / "encoding" / "job_1"
        encode_dir.mkdir(parents=True)
        encode_file = encode_dir / "movie.mkv"
        encode_file.write_text("content")

        database.jobs.append(
            {
                "id": 1,
                "encode_path": str(encode_file),
                "content_type": "movie",
                "identified_title": "Movie",
                "identified_year": 2024,
                "tmdb_id": None,
                "rip_path": None,
                "status": "moving",
                "move_retry_count": 4,  # At custom max
            }
        )

        # Custom max_retries of 5
        mover = FileMover(config, database, max_retries=5)
        await mover._process_jobs()

        # Should still retry (count at 4, max is 5)
        assert "status" not in database.updated_jobs[0]
        assert database.updated_jobs[0]["move_retry_count"] == 5

    @pytest.mark.asyncio
    async def test_init_with_retry_settings(
        self, config: MockConfig, database: MockDatabase
    ) -> None:
        """Should initialize with custom retry settings."""
        mover = FileMover(config, database, max_retries=20, retry_delay=600)
        assert mover.max_retries == 20
        assert mover.retry_delay == 600

    @pytest.mark.asyncio
    async def test_default_retry_settings(
        self, config: MockConfig, database: MockDatabase
    ) -> None:
        """Should use default retry settings if not specified."""
        mover = FileMover(config, database)
        assert mover.max_retries == 10  # DEFAULT_MAX_RETRIES
        assert mover.retry_delay == 300  # DEFAULT_RETRY_DELAY (5 minutes)


class TestFileMoverModeBasedDirectory:
    """Tests for mode-based output directory selection."""

    @pytest.mark.asyncio
    async def test_home_movies_mode_uses_home_movies_dir(
        self, temp_workspace: Path
    ) -> None:
        """HOME_MOVIES mode should use plex_home_movies_dir."""
        from dvdtoplex.database import RipMode

        # Create directories
        plex_home_movies = temp_workspace / "plex_home_movies"
        plex_home_movies.mkdir(exist_ok=True)

        config = MockConfig(
            plex_movies_dir=temp_workspace / "plex_movies",
            plex_tv_dir=temp_workspace / "plex_tv",
            plex_home_movies_dir=plex_home_movies,
            plex_other_dir=temp_workspace / "plex_other",
        )
        (temp_workspace / "plex_movies").mkdir(exist_ok=True)

        # Create test file
        encode_file = temp_workspace / "source.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, MockDatabase())
        result = await mover.move_movie(
            encode_file, "Christmas 2024", None, rip_mode=RipMode.HOME_MOVIES
        )

        assert result.success
        assert result.final_path is not None
        assert str(plex_home_movies) in str(result.final_path)
        assert str(temp_workspace / "plex_movies") not in str(result.final_path)

    @pytest.mark.asyncio
    async def test_other_mode_uses_other_dir(
        self, temp_workspace: Path
    ) -> None:
        """OTHER mode should use plex_other_dir."""
        from dvdtoplex.database import RipMode

        # Create directories
        plex_other = temp_workspace / "plex_other"
        plex_other.mkdir(exist_ok=True)

        config = MockConfig(
            plex_movies_dir=temp_workspace / "plex_movies",
            plex_tv_dir=temp_workspace / "plex_tv",
            plex_home_movies_dir=temp_workspace / "plex_home_movies",
            plex_other_dir=plex_other,
        )
        (temp_workspace / "plex_movies").mkdir(exist_ok=True)

        # Create test file
        encode_file = temp_workspace / "source.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, MockDatabase())
        result = await mover.move_movie(
            encode_file, "Workout Dvd", None, rip_mode=RipMode.OTHER
        )

        assert result.success
        assert result.final_path is not None
        assert str(plex_other) in str(result.final_path)

    @pytest.mark.asyncio
    async def test_movie_mode_uses_movies_dir(
        self, temp_workspace: Path
    ) -> None:
        """MOVIE mode should use plex_movies_dir."""
        from dvdtoplex.database import RipMode

        plex_movies = temp_workspace / "plex_movies"
        plex_movies.mkdir(exist_ok=True)

        config = MockConfig(
            plex_movies_dir=plex_movies,
            plex_tv_dir=temp_workspace / "plex_tv",
            plex_home_movies_dir=temp_workspace / "plex_home_movies",
            plex_other_dir=temp_workspace / "plex_other",
        )

        encode_file = temp_workspace / "source.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, MockDatabase())
        result = await mover.move_movie(
            encode_file, "Inception", 2010, rip_mode=RipMode.MOVIE
        )

        assert result.success
        assert result.final_path is not None
        assert str(plex_movies) in str(result.final_path)

    @pytest.mark.asyncio
    async def test_default_mode_is_movie(
        self, config: MockConfig, temp_workspace: Path
    ) -> None:
        """Default (no mode specified) should use plex_movies_dir."""
        encode_file = temp_workspace / "source.mkv"
        encode_file.write_text("content")

        mover = FileMover(config, MockDatabase())
        result = await mover.move_movie(encode_file, "Test Movie", 2024)

        assert result.success
        assert str(config.plex_movies_dir) in str(result.final_path)
