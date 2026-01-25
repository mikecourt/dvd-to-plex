"""Tests for the database module."""

import pytest
import pytest_asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from dvdtoplex.database import (
    ContentType,
    Database,
    JobStatus,
    RipMode,
)


@pytest_asyncio.fixture
async def db() -> Database:
    """Create a temporary database for testing."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        await database.connect()
        yield database
        await database.close()


class TestEnums:
    """Tests for JobStatus and ContentType enums."""

    def test_job_status_values(self) -> None:
        """JobStatus has all required values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RIPPING.value == "ripping"
        assert JobStatus.RIPPED.value == "ripped"
        assert JobStatus.ENCODING.value == "encoding"
        assert JobStatus.ENCODED.value == "encoded"
        assert JobStatus.IDENTIFYING.value == "identifying"
        assert JobStatus.REVIEW.value == "review"
        assert JobStatus.MOVING.value == "moving"
        assert JobStatus.COMPLETE.value == "complete"
        assert JobStatus.FAILED.value == "failed"

    def test_job_status_has_archived(self) -> None:
        """Test that ARCHIVED status exists in JobStatus enum."""
        assert hasattr(JobStatus, "ARCHIVED")
        assert JobStatus.ARCHIVED.value == "archived"

    def test_content_type_values(self) -> None:
        """ContentType has all required values."""
        assert ContentType.UNKNOWN.value == "unknown"
        assert ContentType.MOVIE.value == "movie"
        assert ContentType.TV_SEASON.value == "tv_season"

    def test_rip_mode_enum_exists(self) -> None:
        """Test that RipMode enum exists with all modes."""
        assert hasattr(RipMode, "MOVIE")
        assert hasattr(RipMode, "TV")
        assert hasattr(RipMode, "HOME_MOVIES")
        assert hasattr(RipMode, "OTHER")
        assert RipMode.MOVIE.value == "movie"
        assert RipMode.TV.value == "tv"
        assert RipMode.HOME_MOVIES.value == "home_movies"
        assert RipMode.OTHER.value == "other"


class TestJobRipMode:
    """Tests for job rip_mode field."""

    @pytest.mark.asyncio
    async def test_job_has_rip_mode_field(self, db: Database) -> None:
        """Test that Job model has rip_mode field."""
        # Create job with explicit mode
        job = await db.create_job("drive0", "TEST_DISC", rip_mode=RipMode.HOME_MOVIES)

        retrieved_job = await db.get_job(job.id)
        assert retrieved_job is not None
        assert retrieved_job.rip_mode == RipMode.HOME_MOVIES

    @pytest.mark.asyncio
    async def test_job_default_rip_mode_is_movie(self, db: Database) -> None:
        """Test that default rip_mode is MOVIE."""
        job = await db.create_job("drive0", "TEST_DISC")

        retrieved_job = await db.get_job(job.id)
        assert retrieved_job is not None
        assert retrieved_job.rip_mode == RipMode.MOVIE


class TestDatabaseConnection:
    """Tests for database connection and initialization."""

    @pytest.mark.asyncio
    async def test_connect_creates_database_file(self) -> None:
        """connect() creates the database file."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            database = Database(db_path)
            await database.connect()
            assert db_path.exists()
            await database.close()

    @pytest.mark.asyncio
    async def test_connection_property_raises_when_not_connected(self) -> None:
        """connection property raises RuntimeError when not connected."""
        with TemporaryDirectory() as tmpdir:
            database = Database(Path(tmpdir) / "test.db")
            with pytest.raises(RuntimeError, match="Database not connected"):
                _ = database.connection

    @pytest.mark.asyncio
    async def test_tables_created_on_connect(self, db: Database) -> None:
        """All tables are created on connect."""
        cursor = await db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        rows = await cursor.fetchall()
        table_names = {row["name"] for row in rows}

        assert "jobs" in table_names
        assert "tv_seasons" in table_names
        assert "episodes" in table_names
        assert "collection" in table_names
        assert "wanted" in table_names
        assert "settings" in table_names

    @pytest.mark.asyncio
    async def test_indexes_created_on_connect(self, db: Database) -> None:
        """Required indexes are created on connect."""
        cursor = await db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        rows = await cursor.fetchall()
        index_names = {row["name"] for row in rows}

        assert "idx_jobs_status" in index_names
        assert "idx_jobs_drive_id" in index_names

    @pytest.mark.asyncio
    async def test_initialize_creates_database_file(self) -> None:
        """initialize() creates the database file (alias for connect)."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            database = Database(db_path)
            await database.initialize()
            assert db_path.exists()
            await database.close()

    @pytest.mark.asyncio
    async def test_is_closed_true_before_connect(self) -> None:
        """is_closed returns True before connect is called."""
        with TemporaryDirectory() as tmpdir:
            database = Database(Path(tmpdir) / "test.db")
            assert database.is_closed is True

    @pytest.mark.asyncio
    async def test_is_closed_false_after_connect(self) -> None:
        """is_closed returns False after connect is called."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            database = Database(db_path)
            await database.connect()
            assert database.is_closed is False
            await database.close()

    @pytest.mark.asyncio
    async def test_is_closed_true_after_close(self) -> None:
        """is_closed returns True after close is called."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            database = Database(db_path)
            await database.connect()
            await database.close()
            assert database.is_closed is True

    @pytest.mark.asyncio
    async def test_initialize_is_alias_for_connect(self) -> None:
        """initialize() behaves the same as connect()."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            database = Database(db_path)
            await database.initialize()
            # Verify connection is established
            assert database.is_closed is False
            # Verify tables were created
            cursor = await database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            rows = await cursor.fetchall()
            table_names = {row["name"] for row in rows}
            assert "jobs" in table_names
            await database.close()


class TestJobOperations:
    """Tests for job CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_job(self, db: Database) -> None:
        """create_job creates a job with pending status."""
        created_job = await db.create_job("drive0", "MY_MOVIE_DISC")

        assert created_job.id > 0
        job = await db.get_job(created_job.id)
        assert job is not None
        assert job.drive_id == "drive0"
        assert job.disc_label == "MY_MOVIE_DISC"
        assert job.status == JobStatus.PENDING
        assert job.content_type == ContentType.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_job_returns_none_for_missing(self, db: Database) -> None:
        """get_job returns None for non-existent job."""
        job = await db.get_job(9999)
        assert job is None

    @pytest.mark.asyncio
    async def test_get_jobs_by_status(self, db: Database) -> None:
        """get_jobs_by_status filters by status."""
        job1 = await db.create_job("drive0", "DISC1")
        job2 = await db.create_job("drive1", "DISC2")
        await db.update_job_status(job2.id, JobStatus.RIPPING)

        pending_jobs = await db.get_jobs_by_status(JobStatus.PENDING)
        ripping_jobs = await db.get_jobs_by_status(JobStatus.RIPPING)

        assert len(pending_jobs) == 1
        assert pending_jobs[0].id == job1.id
        assert len(ripping_jobs) == 1
        assert ripping_jobs[0].id == job2.id

    @pytest.mark.asyncio
    async def test_get_jobs_by_drive(self, db: Database) -> None:
        """get_jobs_by_drive filters by drive_id."""
        await db.create_job("drive0", "DISC1")
        await db.create_job("drive0", "DISC2")
        await db.create_job("drive1", "DISC3")

        drive0_jobs = await db.get_jobs_by_drive("drive0")
        drive1_jobs = await db.get_jobs_by_drive("drive1")

        assert len(drive0_jobs) == 2
        assert len(drive1_jobs) == 1

    @pytest.mark.asyncio
    async def test_get_recent_jobs(self, db: Database) -> None:
        """get_recent_jobs returns jobs in descending order."""
        await db.create_job("drive0", "DISC1")
        await db.create_job("drive0", "DISC2")
        await db.create_job("drive0", "DISC3")

        recent = await db.get_recent_jobs(limit=2)
        assert len(recent) == 2
        assert recent[0].disc_label == "DISC3"
        assert recent[1].disc_label == "DISC2"

    @pytest.mark.asyncio
    async def test_update_job_status(self, db: Database) -> None:
        """update_job_status changes the job status."""
        created_job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(created_job.id, JobStatus.RIPPING)

        job = await db.get_job(created_job.id)
        assert job is not None
        assert job.status == JobStatus.RIPPING

    @pytest.mark.asyncio
    async def test_update_job_status_with_error(self, db: Database) -> None:
        """update_job_status can set error message."""
        created_job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(created_job.id, JobStatus.FAILED, "Drive error")

        job = await db.get_job(created_job.id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert job.error_message == "Drive error"

    @pytest.mark.asyncio
    async def test_update_job_identification(self, db: Database) -> None:
        """update_job_identification updates all identification fields."""
        created_job = await db.create_job("drive0", "DISC1")
        await db.update_job_identification(
            created_job.id,
            content_type=ContentType.MOVIE,
            title="The Matrix",
            year=1999,
            tmdb_id=603,
            confidence=0.95,
        )

        job = await db.get_job(created_job.id)
        assert job is not None
        assert job.content_type == ContentType.MOVIE
        assert job.identified_title == "The Matrix"
        assert job.identified_year == 1999
        assert job.tmdb_id == 603
        assert job.confidence == 0.95

    @pytest.mark.asyncio
    async def test_update_job_identification_with_poster_path(self, db: Database) -> None:
        """update_job_identification stores poster_path when provided."""
        created_job = await db.create_job("drive0", "DISC1")
        await db.update_job_identification(
            created_job.id,
            content_type=ContentType.MOVIE,
            title="Inception",
            year=2010,
            tmdb_id=27205,
            confidence=0.92,
            poster_path="/abc123.jpg",
        )

        job = await db.get_job(created_job.id)
        assert job is not None
        assert job.poster_path == "/abc123.jpg"

    @pytest.mark.asyncio
    async def test_update_job_paths(self, db: Database) -> None:
        """update_job_*_path methods update the respective paths."""
        created_job = await db.create_job("drive0", "DISC1")

        await db.update_job_rip_path(created_job.id, "/rip/path.mkv")
        job = await db.get_job(created_job.id)
        assert job is not None
        assert job.rip_path == "/rip/path.mkv"

        await db.update_job_encode_path(created_job.id, "/encode/path.mkv")
        job = await db.get_job(created_job.id)
        assert job is not None
        assert job.encode_path == "/encode/path.mkv"

        await db.update_job_final_path(created_job.id, "/plex/path.mkv")
        job = await db.get_job(created_job.id)
        assert job is not None
        assert job.final_path == "/plex/path.mkv"


class TestTVSeasonOperations:
    """Tests for TV season CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_tv_season(self, db: Database) -> None:
        """create_tv_season creates a TV season record."""
        created_job = await db.create_job("drive0", "TV_DISC")
        season_id = await db.create_tv_season(
            created_job.id, "Breaking Bad", 1, tmdb_show_id=1396
        )

        assert season_id > 0
        season = await db.get_tv_season(season_id)
        assert season is not None
        assert season.job_id == created_job.id
        assert season.show_title == "Breaking Bad"
        assert season.season_number == 1
        assert season.tmdb_show_id == 1396

    @pytest.mark.asyncio
    async def test_get_tv_season_returns_none_for_missing(self, db: Database) -> None:
        """get_tv_season returns None for non-existent season."""
        season = await db.get_tv_season(9999)
        assert season is None

    @pytest.mark.asyncio
    async def test_get_tv_seasons_by_job(self, db: Database) -> None:
        """get_tv_seasons_by_job returns seasons for a job."""
        created_job = await db.create_job("drive0", "TV_DISC")
        await db.create_tv_season(created_job.id, "Show", 1)
        await db.create_tv_season(created_job.id, "Show", 2)

        seasons = await db.get_tv_seasons_by_job(created_job.id)
        assert len(seasons) == 2
        assert seasons[0].season_number == 1
        assert seasons[1].season_number == 2


class TestEpisodeOperations:
    """Tests for episode CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_episode(self, db: Database) -> None:
        """create_episode creates an episode record."""
        created_job = await db.create_job("drive0", "TV_DISC")
        season_id = await db.create_tv_season(created_job.id, "Show", 1)
        episode_id = await db.create_episode(season_id, 1, "Pilot")

        assert episode_id > 0
        episodes = await db.get_episodes_by_season(season_id)
        assert len(episodes) == 1
        assert episodes[0].episode_number == 1
        assert episodes[0].title == "Pilot"

    @pytest.mark.asyncio
    async def test_get_episodes_by_season_ordered(self, db: Database) -> None:
        """get_episodes_by_season returns episodes in order."""
        created_job = await db.create_job("drive0", "TV_DISC")
        season_id = await db.create_tv_season(created_job.id, "Show", 1)
        await db.create_episode(season_id, 3, "Episode 3")
        await db.create_episode(season_id, 1, "Episode 1")
        await db.create_episode(season_id, 2, "Episode 2")

        episodes = await db.get_episodes_by_season(season_id)
        assert len(episodes) == 3
        assert episodes[0].episode_number == 1
        assert episodes[1].episode_number == 2
        assert episodes[2].episode_number == 3

    @pytest.mark.asyncio
    async def test_update_episode_paths(self, db: Database) -> None:
        """update_episode_paths updates episode paths."""
        created_job = await db.create_job("drive0", "TV_DISC")
        season_id = await db.create_tv_season(created_job.id, "Show", 1)
        episode_id = await db.create_episode(season_id, 1)

        await db.update_episode_paths(
            episode_id,
            rip_path="/rip/ep1.mkv",
            encode_path="/encode/ep1.mkv",
            final_path="/plex/ep1.mkv",
        )

        episodes = await db.get_episodes_by_season(season_id)
        assert episodes[0].rip_path == "/rip/ep1.mkv"
        assert episodes[0].encode_path == "/encode/ep1.mkv"
        assert episodes[0].final_path == "/plex/ep1.mkv"


class TestCollectionOperations:
    """Tests for collection CRUD operations."""

    @pytest.mark.asyncio
    async def test_add_to_collection(self, db: Database) -> None:
        """add_to_collection adds an item to the collection."""
        item_id = await db.add_to_collection(
            ContentType.MOVIE,
            "The Matrix",
            1999,
            603,
            "/plex/Movies/The Matrix (1999)/The Matrix (1999).mkv",
        )

        assert item_id > 0
        item = await db.get_collection_item(item_id)
        assert item is not None
        assert item.title == "The Matrix"
        assert item.year == 1999
        assert item.content_type == ContentType.MOVIE
        assert item.tmdb_id == 603

    @pytest.mark.asyncio
    async def test_get_collection_ordered_by_id_desc(self, db: Database) -> None:
        """get_collection returns items ordered by id descending (most recent first)."""
        await db.add_to_collection(
            ContentType.MOVIE, "First Movie", None, None, "/path/first.mkv"
        )
        await db.add_to_collection(
            ContentType.MOVIE, "Second Movie", None, None, "/path/second.mkv"
        )
        await db.add_to_collection(
            ContentType.MOVIE, "Third Movie", None, None, "/path/third.mkv"
        )

        collection = await db.get_collection()
        assert len(collection) == 3
        # Most recently added should be first (id DESC order)
        assert collection[0]["title"] == "Third Movie"
        assert collection[1]["title"] == "Second Movie"
        assert collection[2]["title"] == "First Movie"

    @pytest.mark.asyncio
    async def test_get_collection_item_returns_none_for_missing(
        self, db: Database
    ) -> None:
        """get_collection_item returns None for non-existent item."""
        item = await db.get_collection_item(9999)
        assert item is None


class TestWantedOperations:
    """Tests for wanted list CRUD operations."""

    @pytest.mark.asyncio
    async def test_add_to_wanted(self, db: Database) -> None:
        """add_to_wanted adds an item to the wanted list."""
        item_id = await db.add_to_wanted(
            title="Inception",
            year=2010,
            content_type=ContentType.MOVIE,
            tmdb_id=27205,
            notes="Looking for director's cut",
        )

        assert item_id > 0
        item = await db.get_wanted_item(item_id)
        assert item is not None
        assert item.title == "Inception"
        assert item.year == 2010
        assert item.notes == "Looking for director's cut"

    @pytest.mark.asyncio
    async def test_get_wanted_ordered_by_added_at_desc(self, db: Database) -> None:
        """get_wanted returns items in reverse chronological order."""
        await db.add_to_wanted("First Movie")
        await db.add_to_wanted("Second Movie")
        await db.add_to_wanted("Third Movie")

        wanted = await db.get_wanted()
        assert len(wanted) == 3
        assert wanted[0].title == "Third Movie"
        assert wanted[1].title == "Second Movie"
        assert wanted[2].title == "First Movie"

    @pytest.mark.asyncio
    async def test_get_wanted_item_returns_none_for_missing(self, db: Database) -> None:
        """get_wanted_item returns None for non-existent item."""
        item = await db.get_wanted_item(9999)
        assert item is None

    @pytest.mark.asyncio
    async def test_remove_from_wanted(self, db: Database) -> None:
        """remove_from_wanted removes an item from the wanted list."""
        item_id = await db.add_to_wanted("Movie to Remove")
        assert await db.get_wanted_item(item_id) is not None

        result = await db.remove_from_wanted(item_id)
        assert result is True
        assert await db.get_wanted_item(item_id) is None

    @pytest.mark.asyncio
    async def test_remove_from_wanted_returns_false_for_missing(
        self, db: Database
    ) -> None:
        """remove_from_wanted returns False for non-existent item."""
        result = await db.remove_from_wanted(9999)
        assert result is False


@pytest.mark.asyncio
async def test_wanted_item_stores_poster_path(tmp_path):
    """Test wanted items can store poster_path."""
    from dvdtoplex.database import Database, ContentType

    db = Database(tmp_path / "test.db")
    await db.connect()

    try:
        item_id = await db.add_to_wanted(
            title="Dune",
            year=2021,
            content_type=ContentType.MOVIE,
            tmdb_id=438631,
            poster_path="/abc123.jpg",
        )

        item = await db.get_wanted_item(item_id)

        assert item is not None
        assert item.poster_path == "/abc123.jpg"
    finally:
        await db.close()


class TestSettingsOperations:
    """Tests for settings CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_setting_returns_default_when_not_set(self, db: Database) -> None:
        """get_setting returns default when setting doesn't exist."""
        value = await db.get_setting("nonexistent", "default_value")
        assert value == "default_value"

    @pytest.mark.asyncio
    async def test_get_setting_returns_none_when_not_set_no_default(
        self, db: Database
    ) -> None:
        """get_setting returns None when no default provided."""
        value = await db.get_setting("nonexistent")
        assert value is None

    @pytest.mark.asyncio
    async def test_set_setting(self, db: Database) -> None:
        """set_setting stores a setting value."""
        await db.set_setting("active_mode", "true")
        value = await db.get_setting("active_mode")
        assert value == "true"

    @pytest.mark.asyncio
    async def test_set_setting_overwrites_existing(self, db: Database) -> None:
        """set_setting overwrites existing value."""
        await db.set_setting("key", "value1")
        await db.set_setting("key", "value2")
        value = await db.get_setting("key")
        assert value == "value2"

    @pytest.mark.asyncio
    async def test_get_all_settings(self, db: Database) -> None:
        """get_all_settings returns all settings as dict."""
        await db.set_setting("key1", "value1")
        await db.set_setting("key2", "value2")

        settings = await db.get_all_settings()
        assert settings == {"key1": "value1", "key2": "value2"}

    @pytest.mark.asyncio
    async def test_get_all_settings_empty(self, db: Database) -> None:
        """get_all_settings returns empty dict when no settings."""
        settings = await db.get_all_settings()
        assert settings == {}
