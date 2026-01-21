"""
Shared pytest fixtures for DVD-to-Plex pipeline tests.

This module provides reusable test fixtures for:
- Configuration with temporary directories
- Real SQLite database instances
- Mock database for unit testing
- Sample data factories for common test scenarios
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pytest
import pytest_asyncio


# ============================================================================
# Configuration Fixtures
# ============================================================================


@dataclass
class Config:
    """Configuration dataclass for testing (mirrors src/dvdtoplex/config.py)."""

    pushover_user_key: str = ""
    pushover_api_token: str = ""
    tmdb_api_token: str = ""
    workspace_dir: Path = field(default_factory=lambda: Path.home() / "DVDWorkspace")
    plex_movies_dir: Path = field(
        default_factory=lambda: Path("/Volumes/Media8TB/Movies")
    )
    plex_tv_dir: Path = field(
        default_factory=lambda: Path("/Volumes/Media8TB/TV Shows")
    )
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    drive_poll_interval: float = 5.0
    auto_approve_threshold: float = 0.85

    @property
    def staging_dir(self) -> Path:
        """Directory for ripped MKV files."""
        return self.workspace_dir / "staging"

    @property
    def encoding_dir(self) -> Path:
        """Directory for encoded files."""
        return self.workspace_dir / "encoding"

    def ensure_directories(self) -> None:
        """Create workspace directories if they don't exist."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.encoding_dir.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Create a test configuration with temporary directories.

    Provides a fully configured Config instance with:
    - Temporary workspace, staging, and encoding directories
    - Temporary Plex movies and TV directories
    - Test API credentials (non-functional placeholders)
    - Fast poll interval for quicker test execution
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "staging").mkdir()
    (workspace / "encoding").mkdir()

    plex_movies = tmp_path / "plex" / "Movies"
    plex_movies.mkdir(parents=True)

    plex_tv = tmp_path / "plex" / "TV Shows"
    plex_tv.mkdir(parents=True)

    return Config(
        pushover_user_key="test_user_key",
        pushover_api_token="test_api_token",
        tmdb_api_token="test_tmdb_token",
        workspace_dir=workspace,
        plex_movies_dir=plex_movies,
        plex_tv_dir=plex_tv,
        web_host="127.0.0.1",
        web_port=8888,
        drive_poll_interval=0.1,  # Fast polling for tests
        auto_approve_threshold=0.85,
    )


@pytest.fixture
def minimal_config() -> Config:
    """Create a minimal config for unit tests that don't need directories.

    Useful for testing code that only reads config values without
    accessing the filesystem.
    """
    return Config(
        pushover_user_key="test_key",
        pushover_api_token="test_token",
        tmdb_api_token="test_tmdb",
        workspace_dir=Path("/tmp/test_workspace"),
        plex_movies_dir=Path("/tmp/test_movies"),
        plex_tv_dir=Path("/tmp/test_tv"),
    )


# ============================================================================
# Database Enums and Data Classes
# ============================================================================


class JobStatus:
    """Job status constants matching the database schema."""

    PENDING = "pending"
    RIPPING = "ripping"
    RIPPED = "ripped"
    ENCODING = "encoding"
    ENCODED = "encoded"
    IDENTIFYING = "identifying"
    REVIEW = "review"
    MOVING = "moving"
    COMPLETE = "complete"
    FAILED = "failed"


class ContentType:
    """Content type constants matching the database schema."""

    UNKNOWN = "unknown"
    MOVIE = "movie"
    TV_SEASON = "tv_season"


@dataclass
class Job:
    """Job dataclass representing a ripping/encoding job."""

    id: int
    drive_id: str
    disc_label: str
    content_type: str = ContentType.UNKNOWN
    status: str = JobStatus.PENDING
    identified_title: Optional[str] = None
    identified_year: Optional[int] = None
    tmdb_id: Optional[int] = None
    confidence: Optional[float] = None
    rip_path: Optional[str] = None
    encode_path: Optional[str] = None
    final_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# Mock Database Fixture
# ============================================================================


class MockDatabase:
    """In-memory mock database for testing without SQLite dependencies.

    Implements the same interface as the real Database class but stores
    everything in memory. Useful for unit tests that don't need persistence.
    """

    def __init__(self) -> None:
        self.jobs: dict[int, Job] = {}
        self.next_job_id: int = 1
        self.tv_seasons: dict[int, dict[str, Any]] = {}
        self.next_season_id: int = 1
        self.episodes: dict[int, dict[str, Any]] = {}
        self.next_episode_id: int = 1
        self.collection: list[dict[str, Any]] = []
        self.wanted: list[dict[str, Any]] = []
        self.settings: dict[str, str] = {"active_mode": "true"}

    async def connect(self) -> None:
        """Initialize the database (no-op for mock)."""
        pass

    async def close(self) -> None:
        """Close the database (no-op for mock)."""
        pass

    # Job operations

    async def create_job(self, drive_id: str, disc_label: str) -> int:
        """Create a new job and return its ID."""
        job_id = self.next_job_id
        self.next_job_id += 1
        self.jobs[job_id] = Job(
            id=job_id,
            drive_id=drive_id,
            disc_label=disc_label,
            status=JobStatus.PENDING,
            content_type=ContentType.UNKNOWN,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return job_id

    async def get_job(self, job_id: int) -> Optional[Job]:
        """Get a job by ID."""
        return self.jobs.get(job_id)

    async def get_jobs_by_status(self, status: str) -> list[Job]:
        """Get all jobs with a specific status."""
        return [job for job in self.jobs.values() if job.status == status]

    async def get_jobs_by_drive(self, drive_id: str) -> list[Job]:
        """Get all jobs for a specific drive."""
        return [job for job in self.jobs.values() if job.drive_id == drive_id]

    async def get_pending_job_for_drive(self, drive_id: str) -> Optional[Job]:
        """Get the first pending job for a specific drive."""
        for job in self.jobs.values():
            if job.status == JobStatus.PENDING and job.drive_id == drive_id:
                return job
        return None

    async def get_recent_jobs(self, limit: int = 10) -> list[Job]:
        """Get the most recent jobs."""
        sorted_jobs = sorted(
            self.jobs.values(),
            key=lambda j: (j.created_at or datetime.min, j.id),
            reverse=True,
        )
        return sorted_jobs[:limit]

    async def update_job_status(
        self,
        job_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update job status."""
        if job_id in self.jobs:
            self.jobs[job_id].status = status
            self.jobs[job_id].updated_at = datetime.now()
            if error_message is not None:
                self.jobs[job_id].error_message = error_message

    async def update_job_rip_path(self, job_id: int, rip_path: str) -> None:
        """Update job rip path."""
        if job_id in self.jobs:
            self.jobs[job_id].rip_path = rip_path
            self.jobs[job_id].updated_at = datetime.now()

    async def update_job_encode_path(self, job_id: int, encode_path: str) -> None:
        """Update job encode path."""
        if job_id in self.jobs:
            self.jobs[job_id].encode_path = encode_path
            self.jobs[job_id].updated_at = datetime.now()

    async def update_job_identification(
        self,
        job_id: int,
        content_type: str,
        title: str,
        year: Optional[int],
        tmdb_id: Optional[int],
        confidence: float,
    ) -> None:
        """Update job identification."""
        if job_id in self.jobs:
            self.jobs[job_id].content_type = content_type
            self.jobs[job_id].identified_title = title
            self.jobs[job_id].identified_year = year
            self.jobs[job_id].tmdb_id = tmdb_id
            self.jobs[job_id].confidence = confidence
            self.jobs[job_id].updated_at = datetime.now()

    async def update_job_final_path(self, job_id: int, final_path: str) -> None:
        """Update job final path."""
        if job_id in self.jobs:
            self.jobs[job_id].final_path = final_path
            self.jobs[job_id].updated_at = datetime.now()

    # TV Season operations

    async def create_tv_season(
        self,
        job_id: int,
        show_title: str,
        season_number: int,
        tmdb_show_id: Optional[int] = None,
    ) -> int:
        """Create a TV season record."""
        season_id = self.next_season_id
        self.next_season_id += 1
        self.tv_seasons[season_id] = {
            "id": season_id,
            "job_id": job_id,
            "show_title": show_title,
            "season_number": season_number,
            "tmdb_show_id": tmdb_show_id,
            "created_at": datetime.now(),
        }
        return season_id

    async def get_tv_season(self, season_id: int) -> Optional[dict[str, Any]]:
        """Get a TV season by ID."""
        return self.tv_seasons.get(season_id)

    async def get_tv_seasons_by_job(self, job_id: int) -> list[dict[str, Any]]:
        """Get all TV seasons for a job."""
        return [s for s in self.tv_seasons.values() if s["job_id"] == job_id]

    # Episode operations

    async def create_episode(
        self,
        season_id: int,
        episode_number: int,
        title: Optional[str] = None,
    ) -> int:
        """Create an episode record."""
        episode_id = self.next_episode_id
        self.next_episode_id += 1
        self.episodes[episode_id] = {
            "id": episode_id,
            "season_id": season_id,
            "episode_number": episode_number,
            "title": title,
            "rip_path": None,
            "encode_path": None,
            "final_path": None,
        }
        return episode_id

    async def get_episodes_by_season(self, season_id: int) -> list[dict[str, Any]]:
        """Get all episodes for a TV season."""
        episodes = [e for e in self.episodes.values() if e["season_id"] == season_id]
        return sorted(episodes, key=lambda e: e["episode_number"])

    async def update_episode_paths(
        self,
        episode_id: int,
        rip_path: Optional[str] = None,
        encode_path: Optional[str] = None,
        final_path: Optional[str] = None,
    ) -> None:
        """Update episode file paths."""
        if episode_id in self.episodes:
            if rip_path is not None:
                self.episodes[episode_id]["rip_path"] = rip_path
            if encode_path is not None:
                self.episodes[episode_id]["encode_path"] = encode_path
            if final_path is not None:
                self.episodes[episode_id]["final_path"] = final_path

    # Collection operations

    async def add_to_collection(
        self,
        title: str,
        file_path: str,
        year: Optional[int] = None,
        content_type: str = ContentType.MOVIE,
        tmdb_id: Optional[int] = None,
    ) -> int:
        """Add an item to the collection."""
        item_id = len(self.collection) + 1
        self.collection.append(
            {
                "id": item_id,
                "title": title,
                "year": year,
                "content_type": content_type,
                "tmdb_id": tmdb_id,
                "file_path": file_path,
                "added_at": datetime.now(),
            }
        )
        return item_id

    async def get_collection(self) -> list[dict[str, Any]]:
        """Get all items in the collection."""
        return sorted(self.collection, key=lambda x: x["title"])

    async def get_collection_item(self, item_id: int) -> Optional[dict[str, Any]]:
        """Get a collection item by ID."""
        for item in self.collection:
            if item["id"] == item_id:
                return item
        return None

    # Wanted list operations

    async def add_to_wanted(
        self,
        title: str,
        year: Optional[int] = None,
        content_type: str = ContentType.MOVIE,
        tmdb_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        """Add an item to the wanted list."""
        item_id = len(self.wanted) + 1
        self.wanted.append(
            {
                "id": item_id,
                "title": title,
                "year": year,
                "content_type": content_type,
                "tmdb_id": tmdb_id,
                "notes": notes,
                "added_at": datetime.now(),
            }
        )
        return item_id

    async def get_wanted(self) -> list[dict[str, Any]]:
        """Get all items in the wanted list."""
        return list(reversed(self.wanted))  # Most recent first

    async def get_wanted_item(self, item_id: int) -> Optional[dict[str, Any]]:
        """Get a wanted item by ID."""
        for item in self.wanted:
            if item["id"] == item_id:
                return item
        return None

    async def remove_from_wanted(self, item_id: int) -> bool:
        """Remove an item from the wanted list."""
        for i, item in enumerate(self.wanted):
            if item["id"] == item_id:
                self.wanted.pop(i)
                return True
        return False

    # Settings operations

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a setting value."""
        return self.settings.get(key, default)

    async def set_setting(self, key: str, value: str) -> None:
        """Set a setting value."""
        self.settings[key] = value

    async def get_all_settings(self) -> dict[str, str]:
        """Get all settings as a dictionary."""
        return dict(self.settings)


@pytest.fixture
def mock_database() -> MockDatabase:
    """Create a mock in-memory database for testing.

    The mock database provides the same interface as the real Database
    class but stores everything in memory. Reset between tests.
    """
    return MockDatabase()


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@dataclass
class SampleMovie:
    """Sample movie data for testing."""

    disc_label: str
    title: str
    year: int
    tmdb_id: int
    confidence: float = 0.95


@dataclass
class SampleTVSeason:
    """Sample TV season data for testing."""

    disc_label: str
    show_title: str
    season_number: int
    tmdb_show_id: int
    episode_count: int
    confidence: float = 0.90


class SampleData:
    """Factory for creating sample test data."""

    # Classic movies for testing
    MOVIES = [
        SampleMovie("THE_MATRIX_1999", "The Matrix", 1999, 603, 0.98),
        SampleMovie("INCEPTION_2010", "Inception", 2010, 27205, 0.96),
        SampleMovie("BLADE_RUNNER", "Blade Runner", 1982, 78, 0.94),
        SampleMovie("GODFATHER_1972", "The Godfather", 1972, 238, 0.97),
        SampleMovie("STAR_WARS_1977", "Star Wars: Episode IV - A New Hope", 1977, 11, 0.99),
        SampleMovie("JURASSIC_PARK", "Jurassic Park", 1993, 329, 0.95),
        SampleMovie("BACK_TO_FUTURE", "Back to the Future", 1985, 105, 0.93),
    ]

    # Low confidence movies (need review)
    LOW_CONFIDENCE_MOVIES = [
        SampleMovie("UNKNOWN_DISC_1", "Possible Match", 2020, 99999, 0.45),
        SampleMovie("SCRATCHED_DVD", "Maybe This One", 2015, 88888, 0.55),
        SampleMovie("NO_LABEL", "Unknown Film", 2018, 77777, 0.30),
    ]

    # TV seasons for testing
    TV_SEASONS = [
        SampleTVSeason("FRIENDS_S01", "Friends", 1, 1668, 24, 0.92),
        SampleTVSeason("BREAKING_BAD_S01", "Breaking Bad", 1, 1396, 7, 0.95),
        SampleTVSeason("OFFICE_S02", "The Office", 2, 2316, 22, 0.91),
        SampleTVSeason("STRANGER_THINGS_S01", "Stranger Things", 1, 66732, 8, 0.94),
    ]

    @classmethod
    def get_movie(cls, index: int = 0) -> SampleMovie:
        """Get a sample movie by index."""
        return cls.MOVIES[index % len(cls.MOVIES)]

    @classmethod
    def get_low_confidence_movie(cls, index: int = 0) -> SampleMovie:
        """Get a low confidence sample movie by index."""
        return cls.LOW_CONFIDENCE_MOVIES[index % len(cls.LOW_CONFIDENCE_MOVIES)]

    @classmethod
    def get_tv_season(cls, index: int = 0) -> SampleTVSeason:
        """Get a sample TV season by index."""
        return cls.TV_SEASONS[index % len(cls.TV_SEASONS)]


@pytest.fixture
def sample_data() -> type[SampleData]:
    """Provide access to sample test data factory.

    Usage:
        def test_something(sample_data):
            movie = sample_data.get_movie()
            tv = sample_data.get_tv_season()
    """
    return SampleData


@pytest.fixture
def sample_movie() -> SampleMovie:
    """Provide a single sample movie for simple tests."""
    return SampleData.get_movie(0)


@pytest.fixture
def sample_tv_season() -> SampleTVSeason:
    """Provide a single sample TV season for simple tests."""
    return SampleData.get_tv_season(0)


# ============================================================================
# Database with Sample Data Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def mock_database_with_jobs(mock_database: MockDatabase) -> MockDatabase:
    """Create a mock database pre-populated with sample jobs.

    Includes jobs in various states for testing state transitions.
    """
    # Pending job
    await mock_database.create_job("disk0", "PENDING_DISC")

    # Ripping job
    job_id = await mock_database.create_job("disk1", "RIPPING_DISC")
    await mock_database.update_job_status(job_id, JobStatus.RIPPING)

    # Encoded job (ready for identification)
    job_id = await mock_database.create_job("disk0", "ENCODED_DISC")
    await mock_database.update_job_status(job_id, JobStatus.ENCODED)
    await mock_database.update_job_rip_path(job_id, "/staging/encoded_disc.mkv")
    await mock_database.update_job_encode_path(job_id, "/encoding/encoded_disc.mkv")

    # Review job (needs manual approval)
    job_id = await mock_database.create_job("disk0", "REVIEW_DISC")
    await mock_database.update_job_identification(
        job_id, ContentType.MOVIE, "Possible Match", 2020, 12345, 0.5
    )
    await mock_database.update_job_status(job_id, JobStatus.REVIEW)

    # Complete job
    job_id = await mock_database.create_job("disk0", "THE_MATRIX_1999")
    await mock_database.update_job_identification(
        job_id, ContentType.MOVIE, "The Matrix", 1999, 603, 0.98
    )
    await mock_database.update_job_final_path(
        job_id, "/plex/Movies/The Matrix (1999)/The Matrix (1999).mkv"
    )
    await mock_database.update_job_status(job_id, JobStatus.COMPLETE)

    # Failed job
    job_id = await mock_database.create_job("disk1", "BAD_DISC")
    await mock_database.update_job_status(job_id, JobStatus.FAILED, "Unreadable disc")

    return mock_database


@pytest_asyncio.fixture
async def mock_database_with_collection(mock_database: MockDatabase) -> MockDatabase:
    """Create a mock database pre-populated with collection items."""
    await mock_database.add_to_collection(
        "The Matrix", "/movies/matrix.mkv", 1999, ContentType.MOVIE, 603
    )
    await mock_database.add_to_collection(
        "Inception", "/movies/inception.mkv", 2010, ContentType.MOVIE, 27205
    )
    await mock_database.add_to_collection(
        "Breaking Bad", "/tv/breaking_bad/s01.mkv", 2008, ContentType.TV_SEASON, 1396
    )
    return mock_database


@pytest_asyncio.fixture
async def mock_database_with_wanted(mock_database: MockDatabase) -> MockDatabase:
    """Create a mock database pre-populated with wanted items."""
    await mock_database.add_to_wanted(
        "Blade Runner 2049", 2017, ContentType.MOVIE, 335984, "Director's cut preferred"
    )
    await mock_database.add_to_wanted(
        "The Shawshank Redemption", 1994, ContentType.MOVIE, 278
    )
    await mock_database.add_to_wanted(
        "Game of Thrones", 2011, ContentType.TV_SEASON, 1399, "Looking for Season 1"
    )
    return mock_database
