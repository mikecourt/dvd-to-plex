"""Tests for the shared test fixtures.

This module verifies that the fixtures in conftest.py work correctly.
"""

import pytest
from pathlib import Path

from tests.conftest import (
    Config,
    ContentType,
    JobStatus,
    MockDatabase,
    SampleData,
    SampleMovie,
    SampleTVSeason,
)


class TestConfigFixture:
    """Tests for the configuration fixture."""

    def test_config_has_temp_directories(self, test_config: Config) -> None:
        """Test that config uses temporary directories that exist."""
        assert test_config.workspace_dir.exists()
        assert test_config.plex_movies_dir.exists()
        assert test_config.plex_tv_dir.exists()

    def test_config_staging_and_encoding_dirs_exist(self, test_config: Config) -> None:
        """Test that staging and encoding directories exist."""
        assert test_config.staging_dir.exists()
        assert test_config.encoding_dir.exists()

    def test_config_has_test_credentials(self, test_config: Config) -> None:
        """Test that config has test credentials."""
        assert test_config.pushover_user_key == "test_user_key"
        assert test_config.pushover_api_token == "test_api_token"
        assert test_config.tmdb_api_token == "test_tmdb_token"

    def test_config_has_fast_poll_interval(self, test_config: Config) -> None:
        """Test that config has fast poll interval for testing."""
        assert test_config.drive_poll_interval == 0.1

    def test_config_auto_approve_threshold(self, test_config: Config) -> None:
        """Test that auto approve threshold is set."""
        assert test_config.auto_approve_threshold == 0.85

    def test_minimal_config_no_directories(self, minimal_config: Config) -> None:
        """Test that minimal config doesn't require directory creation."""
        assert minimal_config.workspace_dir == Path("/tmp/test_workspace")
        assert minimal_config.pushover_user_key == "test_key"


class TestMockDatabaseFixture:
    """Tests for the mock database fixture."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_job(self, mock_database: MockDatabase) -> None:
        """Test creating and retrieving a job."""
        job_id = await mock_database.create_job("disk0", "TEST_DISC")
        job = await mock_database.get_job(job_id)

        assert job is not None
        assert job.id == job_id
        assert job.drive_id == "disk0"
        assert job.disc_label == "TEST_DISC"
        assert job.status == JobStatus.PENDING
        assert job.content_type == ContentType.UNKNOWN

    @pytest.mark.asyncio
    async def test_update_job_status(self, mock_database: MockDatabase) -> None:
        """Test updating job status."""
        job_id = await mock_database.create_job("disk0", "TEST_DISC")
        await mock_database.update_job_status(job_id, JobStatus.RIPPING)

        job = await mock_database.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.RIPPING

    @pytest.mark.asyncio
    async def test_update_job_status_with_error(self, mock_database: MockDatabase) -> None:
        """Test updating job status with error message."""
        job_id = await mock_database.create_job("disk0", "TEST_DISC")
        await mock_database.update_job_status(job_id, JobStatus.FAILED, "Test error")

        job = await mock_database.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert job.error_message == "Test error"

    @pytest.mark.asyncio
    async def test_get_jobs_by_status(self, mock_database: MockDatabase) -> None:
        """Test getting jobs by status."""
        job1_id = await mock_database.create_job("disk0", "DISC_1")
        _job2_id = await mock_database.create_job("disk1", "DISC_2")
        await mock_database.update_job_status(job1_id, JobStatus.RIPPING)

        pending_jobs = await mock_database.get_jobs_by_status(JobStatus.PENDING)
        ripping_jobs = await mock_database.get_jobs_by_status(JobStatus.RIPPING)

        assert len(pending_jobs) == 1
        assert pending_jobs[0].disc_label == "DISC_2"
        assert len(ripping_jobs) == 1
        assert ripping_jobs[0].disc_label == "DISC_1"

    @pytest.mark.asyncio
    async def test_get_pending_job_for_drive(self, mock_database: MockDatabase) -> None:
        """Test getting pending job for a specific drive."""
        await mock_database.create_job("disk0", "DISC_1")
        await mock_database.create_job("disk1", "DISC_2")

        job = await mock_database.get_pending_job_for_drive("disk0")
        assert job is not None
        assert job.disc_label == "DISC_1"

        job = await mock_database.get_pending_job_for_drive("disk2")
        assert job is None

    @pytest.mark.asyncio
    async def test_update_job_paths(self, mock_database: MockDatabase) -> None:
        """Test updating job paths."""
        job_id = await mock_database.create_job("disk0", "TEST_DISC")

        await mock_database.update_job_rip_path(job_id, "/staging/test.mkv")
        await mock_database.update_job_encode_path(job_id, "/encoding/test.mkv")
        await mock_database.update_job_final_path(job_id, "/movies/test.mkv")

        job = await mock_database.get_job(job_id)
        assert job is not None
        assert job.rip_path == "/staging/test.mkv"
        assert job.encode_path == "/encoding/test.mkv"
        assert job.final_path == "/movies/test.mkv"

    @pytest.mark.asyncio
    async def test_update_job_identification(self, mock_database: MockDatabase) -> None:
        """Test updating job identification."""
        job_id = await mock_database.create_job("disk0", "THE_MATRIX")

        await mock_database.update_job_identification(
            job_id,
            ContentType.MOVIE,
            "The Matrix",
            1999,
            603,
            0.95,
        )

        job = await mock_database.get_job(job_id)
        assert job is not None
        assert job.content_type == ContentType.MOVIE
        assert job.identified_title == "The Matrix"
        assert job.identified_year == 1999
        assert job.tmdb_id == 603
        assert job.confidence == 0.95

    @pytest.mark.asyncio
    async def test_get_recent_jobs(self, mock_database: MockDatabase) -> None:
        """Test getting recent jobs."""
        for i in range(15):
            await mock_database.create_job("disk0", f"DISC_{i}")

        recent = await mock_database.get_recent_jobs(10)
        assert len(recent) == 10

        recent = await mock_database.get_recent_jobs(5)
        assert len(recent) == 5


class TestTVSeasonOperations:
    """Tests for TV season database operations."""

    @pytest.mark.asyncio
    async def test_create_tv_season(self, mock_database: MockDatabase) -> None:
        """Test creating a TV season."""
        job_id = await mock_database.create_job("disk0", "FRIENDS_S01")
        season_id = await mock_database.create_tv_season(job_id, "Friends", 1, 1668)

        season = await mock_database.get_tv_season(season_id)
        assert season is not None
        assert season["job_id"] == job_id
        assert season["show_title"] == "Friends"
        assert season["season_number"] == 1
        assert season["tmdb_show_id"] == 1668

    @pytest.mark.asyncio
    async def test_get_tv_seasons_by_job(self, mock_database: MockDatabase) -> None:
        """Test getting TV seasons for a job."""
        job_id = await mock_database.create_job("disk0", "MULTI_SEASON")
        await mock_database.create_tv_season(job_id, "Show", 1)
        await mock_database.create_tv_season(job_id, "Show", 2)

        seasons = await mock_database.get_tv_seasons_by_job(job_id)
        assert len(seasons) == 2


class TestEpisodeOperations:
    """Tests for episode database operations."""

    @pytest.mark.asyncio
    async def test_create_episode(self, mock_database: MockDatabase) -> None:
        """Test creating an episode."""
        job_id = await mock_database.create_job("disk0", "FRIENDS_S01")
        season_id = await mock_database.create_tv_season(job_id, "Friends", 1)
        _episode_id = await mock_database.create_episode(season_id, 1, "The Pilot")

        episodes = await mock_database.get_episodes_by_season(season_id)
        assert len(episodes) == 1
        assert episodes[0]["title"] == "The Pilot"
        assert episodes[0]["episode_number"] == 1

    @pytest.mark.asyncio
    async def test_update_episode_paths(self, mock_database: MockDatabase) -> None:
        """Test updating episode paths."""
        job_id = await mock_database.create_job("disk0", "FRIENDS_S01")
        season_id = await mock_database.create_tv_season(job_id, "Friends", 1)
        episode_id = await mock_database.create_episode(season_id, 1)

        await mock_database.update_episode_paths(
            episode_id,
            rip_path="/staging/ep1.mkv",
            encode_path="/encoding/ep1.mkv",
            final_path="/tv/friends/s01e01.mkv",
        )

        episodes = await mock_database.get_episodes_by_season(season_id)
        assert episodes[0]["rip_path"] == "/staging/ep1.mkv"
        assert episodes[0]["encode_path"] == "/encoding/ep1.mkv"
        assert episodes[0]["final_path"] == "/tv/friends/s01e01.mkv"


class TestCollectionOperations:
    """Tests for collection database operations."""

    @pytest.mark.asyncio
    async def test_add_to_collection(self, mock_database: MockDatabase) -> None:
        """Test adding to collection."""
        _item_id = await mock_database.add_to_collection(
            "The Matrix",
            "/movies/matrix.mkv",
            1999,
            ContentType.MOVIE,
            603,
        )

        collection = await mock_database.get_collection()
        assert len(collection) == 1
        assert collection[0]["title"] == "The Matrix"
        assert collection[0]["year"] == 1999

    @pytest.mark.asyncio
    async def test_get_collection_item(self, mock_database: MockDatabase) -> None:
        """Test getting a collection item."""
        item_id = await mock_database.add_to_collection(
            "Inception", "/movies/inception.mkv", 2010
        )

        item = await mock_database.get_collection_item(item_id)
        assert item is not None
        assert item["title"] == "Inception"

    @pytest.mark.asyncio
    async def test_collection_sorted_by_title(self, mock_database: MockDatabase) -> None:
        """Test that collection is sorted by title."""
        await mock_database.add_to_collection("Zulu", "/movies/zulu.mkv")
        await mock_database.add_to_collection("Alien", "/movies/alien.mkv")

        collection = await mock_database.get_collection()
        assert collection[0]["title"] == "Alien"
        assert collection[1]["title"] == "Zulu"


class TestWantedOperations:
    """Tests for wanted list database operations."""

    @pytest.mark.asyncio
    async def test_add_to_wanted(self, mock_database: MockDatabase) -> None:
        """Test adding to wanted list."""
        _item_id = await mock_database.add_to_wanted(
            "Blade Runner",
            1982,
            ContentType.MOVIE,
            78,
            "Director's cut",
        )

        wanted = await mock_database.get_wanted()
        assert len(wanted) == 1
        assert wanted[0]["title"] == "Blade Runner"
        assert wanted[0]["notes"] == "Director's cut"

    @pytest.mark.asyncio
    async def test_remove_from_wanted(self, mock_database: MockDatabase) -> None:
        """Test removing from wanted list."""
        item_id = await mock_database.add_to_wanted("Test Movie")

        result = await mock_database.remove_from_wanted(item_id)
        assert result is True

        wanted = await mock_database.get_wanted()
        assert len(wanted) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_from_wanted(self, mock_database: MockDatabase) -> None:
        """Test removing nonexistent item from wanted list."""
        result = await mock_database.remove_from_wanted(999)
        assert result is False


class TestSettingsOperations:
    """Tests for settings database operations."""

    @pytest.mark.asyncio
    async def test_set_and_get_setting(self, mock_database: MockDatabase) -> None:
        """Test setting and getting a setting."""
        await mock_database.set_setting("test_key", "test_value")
        value = await mock_database.get_setting("test_key")
        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_get_setting_default(self, mock_database: MockDatabase) -> None:
        """Test getting a setting with default value."""
        value = await mock_database.get_setting("nonexistent", "default")
        assert value == "default"

    @pytest.mark.asyncio
    async def test_get_all_settings(self, mock_database: MockDatabase) -> None:
        """Test getting all settings."""
        await mock_database.set_setting("key1", "value1")
        await mock_database.set_setting("key2", "value2")

        settings = await mock_database.get_all_settings()
        assert "key1" in settings
        assert "key2" in settings
        assert "active_mode" in settings  # Default setting


class TestSampleDataFixture:
    """Tests for the sample data fixture."""

    def test_get_movie(self, sample_data: type[SampleData]) -> None:
        """Test getting a sample movie."""
        movie = sample_data.get_movie(0)
        assert isinstance(movie, SampleMovie)
        assert movie.title == "The Matrix"
        assert movie.year == 1999

    def test_get_movie_wraps_around(self, sample_data: type[SampleData]) -> None:
        """Test that get_movie wraps around for large indices."""
        movie1 = sample_data.get_movie(0)
        movie2 = sample_data.get_movie(len(sample_data.MOVIES))
        assert movie1.title == movie2.title

    def test_get_low_confidence_movie(self, sample_data: type[SampleData]) -> None:
        """Test getting a low confidence movie."""
        movie = sample_data.get_low_confidence_movie(0)
        assert movie.confidence < 0.85

    def test_get_tv_season(self, sample_data: type[SampleData]) -> None:
        """Test getting a sample TV season."""
        tv = sample_data.get_tv_season(0)
        assert isinstance(tv, SampleTVSeason)
        assert tv.show_title == "Friends"
        assert tv.season_number == 1

    def test_sample_movie_fixture(self, sample_movie: SampleMovie) -> None:
        """Test the simple sample_movie fixture."""
        assert sample_movie.title == "The Matrix"

    def test_sample_tv_season_fixture(self, sample_tv_season: SampleTVSeason) -> None:
        """Test the simple sample_tv_season fixture."""
        assert sample_tv_season.show_title == "Friends"


class TestPrePopulatedDatabaseFixtures:
    """Tests for pre-populated database fixtures."""

    @pytest.mark.asyncio
    async def test_database_with_jobs(self, mock_database_with_jobs: MockDatabase) -> None:
        """Test that database is pre-populated with jobs in various states."""
        pending = await mock_database_with_jobs.get_jobs_by_status(JobStatus.PENDING)
        ripping = await mock_database_with_jobs.get_jobs_by_status(JobStatus.RIPPING)
        encoded = await mock_database_with_jobs.get_jobs_by_status(JobStatus.ENCODED)
        review = await mock_database_with_jobs.get_jobs_by_status(JobStatus.REVIEW)
        complete = await mock_database_with_jobs.get_jobs_by_status(JobStatus.COMPLETE)
        failed = await mock_database_with_jobs.get_jobs_by_status(JobStatus.FAILED)

        assert len(pending) >= 1
        assert len(ripping) >= 1
        assert len(encoded) >= 1
        assert len(review) >= 1
        assert len(complete) >= 1
        assert len(failed) >= 1

    @pytest.mark.asyncio
    async def test_database_with_collection(
        self, mock_database_with_collection: MockDatabase
    ) -> None:
        """Test that database is pre-populated with collection items."""
        collection = await mock_database_with_collection.get_collection()
        assert len(collection) >= 3

        titles = [item["title"] for item in collection]
        assert "The Matrix" in titles
        assert "Inception" in titles

    @pytest.mark.asyncio
    async def test_database_with_wanted(
        self, mock_database_with_wanted: MockDatabase
    ) -> None:
        """Test that database is pre-populated with wanted items."""
        wanted = await mock_database_with_wanted.get_wanted()
        assert len(wanted) >= 3

        titles = [item["title"] for item in wanted]
        assert "Blade Runner 2049" in titles
        assert "The Shawshank Redemption" in titles
