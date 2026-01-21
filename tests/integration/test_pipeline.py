"""
Integration tests for the DVD-to-Plex pipeline.

Tests job state transitions through the full lifecycle:
pending -> ripping -> ripped -> encoding -> encoded -> identifying -> review/moving -> complete

Provides test fixtures for config and database.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import pytest


# ============================================================================
# Enums and Data Classes (mirrors src/dvdtoplex/database.py)
# ============================================================================


class JobStatus(str, Enum):
    """Job status enum matching the database schema."""

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


class ContentType(str, Enum):
    """Content type enum matching the database schema."""

    UNKNOWN = "unknown"
    MOVIE = "movie"
    TV_SEASON = "tv_season"


@dataclass
class Config:
    """Configuration dataclass for the pipeline."""

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
    poll_interval: float = 5.0
    auto_approve_threshold: float = 0.85


@dataclass
class Job:
    """Job dataclass representing a ripping/encoding job."""

    id: int
    drive_id: str
    disc_label: str
    content_type: ContentType = ContentType.UNKNOWN
    status: JobStatus = JobStatus.PENDING
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


@dataclass
class TitleInfo:
    """MakeMKV title information."""

    index: int
    duration_seconds: int
    size_bytes: int
    filename: str


@dataclass
class MovieMatch:
    """TMDb movie match result."""

    tmdb_id: int
    title: str
    year: int
    overview: str
    poster_path: Optional[str]
    popularity: float


@dataclass
class IdentificationResult:
    """Result from content identification."""

    content_type: ContentType
    title: str
    year: int
    tmdb_id: int
    confidence: float
    needs_review: bool
    alternatives: list[MovieMatch]


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Create a test configuration with temporary directories."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

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
        poll_interval=0.1,  # Fast polling for tests
        auto_approve_threshold=0.85,
    )


@pytest.fixture
def mock_database() -> "MockDatabase":
    """Create a mock database for testing."""
    return MockDatabase()


class MockDatabase:
    """Mock database for integration testing."""

    def __init__(self) -> None:
        self.jobs: dict[int, Job] = {}
        self.next_job_id: int = 1
        self.collection: list[dict[str, Any]] = []
        self.wanted: list[dict[str, Any]] = []
        self.settings: dict[str, str] = {"active_mode": "true"}

    async def init(self) -> None:
        """Initialize the database (no-op for mock)."""
        pass

    async def close(self) -> None:
        """Close the database (no-op for mock)."""
        pass

    async def create_job(self, drive_id: str, disc_label: str) -> int:
        """Create a new job and return its ID."""
        job_id = self.next_job_id
        self.next_job_id += 1
        self.jobs[job_id] = Job(
            id=job_id,
            drive_id=drive_id,
            disc_label=disc_label,
            status=JobStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return job_id

    async def get_job(self, job_id: int) -> Optional[Job]:
        """Get a job by ID."""
        return self.jobs.get(job_id)

    async def get_jobs_by_status(self, status: JobStatus) -> list[Job]:
        """Get all jobs with a specific status."""
        return [job for job in self.jobs.values() if job.status == status]

    async def get_pending_jobs_for_drive(self, drive_id: str) -> list[Job]:
        """Get pending jobs for a specific drive."""
        return [
            job
            for job in self.jobs.values()
            if job.status == JobStatus.PENDING and job.drive_id == drive_id
        ]

    async def update_job_status(
        self,
        job_id: int,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> None:
        """Update job status."""
        if job_id in self.jobs:
            self.jobs[job_id].status = status
            self.jobs[job_id].updated_at = datetime.now()
            if error_message:
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
        content_type: ContentType,
        title: str,
        year: int,
        tmdb_id: int,
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

    async def add_to_collection(
        self,
        title: str,
        year: int,
        tmdb_id: int,
        content_type: ContentType,
        file_path: str,
    ) -> int:
        """Add an item to the collection."""
        item_id = len(self.collection) + 1
        self.collection.append(
            {
                "id": item_id,
                "title": title,
                "year": year,
                "tmdb_id": tmdb_id,
                "content_type": content_type.value,
                "file_path": file_path,
            }
        )
        return item_id

    async def get_setting(self, key: str) -> Optional[str]:
        """Get a setting value."""
        return self.settings.get(key)

    async def set_setting(self, key: str, value: str) -> None:
        """Set a setting value."""
        self.settings[key] = value


# ============================================================================
# Mock Services for Integration Testing
# ============================================================================


class MockDriveWatcher:
    """Mock drive watcher that can simulate disc insertion."""

    def __init__(self, database: MockDatabase, config: Config) -> None:
        self.database = database
        self.config = config
        self.running = False
        self._task: Optional[asyncio.Task[None]] = None
        self.disc_insertions: list[tuple[str, str]] = []

    async def start(self) -> None:
        """Start the drive watcher."""
        self.running = True

    async def stop(self) -> None:
        """Stop the drive watcher."""
        self.running = False
        if self._task:
            self._task.cancel()

    async def simulate_disc_insertion(self, drive_id: str, disc_label: str) -> int:
        """Simulate inserting a disc and create a job."""
        self.disc_insertions.append((drive_id, disc_label))
        job_id = await self.database.create_job(drive_id, disc_label)
        return job_id


class MockRipQueue:
    """Mock rip queue that simulates the ripping process."""

    def __init__(
        self, database: MockDatabase, config: Config, on_rip_complete: Optional[Callable[[int], None]] = None
    ) -> None:
        self.database = database
        self.config = config
        self.running = False
        self.on_rip_complete = on_rip_complete
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start the rip queue processor."""
        self.running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop the rip queue processor."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self) -> None:
        """Process pending rip jobs."""
        while self.running:
            pending_jobs = await self.database.get_jobs_by_status(JobStatus.PENDING)
            for job in pending_jobs:
                await self._process_job(job)
            await asyncio.sleep(0.01)

    async def _process_job(self, job: Job) -> None:
        """Process a single rip job."""
        await self.database.update_job_status(job.id, JobStatus.RIPPING)

        # Simulate ripping
        rip_dir = self.config.workspace_dir / "rips" / f"job_{job.id}"
        rip_dir.mkdir(parents=True, exist_ok=True)
        rip_path = rip_dir / f"{job.disc_label}.mkv"
        rip_path.write_bytes(b"mock mkv content")

        await self.database.update_job_rip_path(job.id, str(rip_path))
        await self.database.update_job_status(job.id, JobStatus.RIPPED)

        if self.on_rip_complete:
            self.on_rip_complete(job.id)


class MockEncodeQueue:
    """Mock encode queue that simulates the encoding process."""

    def __init__(
        self, database: MockDatabase, config: Config, on_encode_complete: Optional[Callable[[int], None]] = None
    ) -> None:
        self.database = database
        self.config = config
        self.running = False
        self.on_encode_complete = on_encode_complete
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start the encode queue processor."""
        self.running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop the encode queue processor."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self) -> None:
        """Process ripped jobs that need encoding."""
        while self.running:
            ripped_jobs = await self.database.get_jobs_by_status(JobStatus.RIPPED)
            for job in ripped_jobs:
                await self._process_job(job)
            await asyncio.sleep(0.01)

    async def _process_job(self, job: Job) -> None:
        """Process a single encode job."""
        await self.database.update_job_status(job.id, JobStatus.ENCODING)

        # Simulate encoding
        encode_dir = self.config.workspace_dir / "encodes" / f"job_{job.id}"
        encode_dir.mkdir(parents=True, exist_ok=True)
        encode_path = encode_dir / f"{job.disc_label}_encoded.mkv"
        encode_path.write_bytes(b"mock encoded mkv content")

        await self.database.update_job_encode_path(job.id, str(encode_path))
        await self.database.update_job_status(job.id, JobStatus.ENCODED)

        if self.on_encode_complete:
            self.on_encode_complete(job.id)


class MockIdentifierService:
    """Mock identifier service that simulates content identification."""

    def __init__(
        self,
        database: MockDatabase,
        config: Config,
        default_confidence: float = 0.9,
    ) -> None:
        self.database = database
        self.config = config
        self.running = False
        self.default_confidence = default_confidence
        self._task: Optional[asyncio.Task[None]] = None
        # Map disc labels to identification results
        self.identification_map: dict[str, IdentificationResult] = {}

    def set_identification(
        self, disc_label: str, result: IdentificationResult
    ) -> None:
        """Set the identification result for a disc label."""
        self.identification_map[disc_label] = result

    async def start(self) -> None:
        """Start the identifier service."""
        self.running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop the identifier service."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self) -> None:
        """Process encoded jobs that need identification."""
        while self.running:
            encoded_jobs = await self.database.get_jobs_by_status(JobStatus.ENCODED)
            for job in encoded_jobs:
                await self._process_job(job)
            await asyncio.sleep(0.01)

    async def _process_job(self, job: Job) -> None:
        """Process a single identification job."""
        await self.database.update_job_status(job.id, JobStatus.IDENTIFYING)

        # Get identification result (use preset or generate from disc label)
        if job.disc_label in self.identification_map:
            result = self.identification_map[job.disc_label]
        else:
            # Generate default identification from disc label
            result = IdentificationResult(
                content_type=ContentType.MOVIE,
                title=job.disc_label.replace("_", " ").title(),
                year=2023,
                tmdb_id=12345,
                confidence=self.default_confidence,
                needs_review=self.default_confidence < self.config.auto_approve_threshold,
                alternatives=[],
            )

        await self.database.update_job_identification(
            job.id,
            result.content_type,
            result.title,
            result.year,
            result.tmdb_id,
            result.confidence,
        )

        if result.needs_review:
            await self.database.update_job_status(job.id, JobStatus.REVIEW)
        else:
            await self.database.update_job_status(job.id, JobStatus.MOVING)


class MockFileMover:
    """Mock file mover that simulates moving files to Plex library."""

    def __init__(self, database: MockDatabase, config: Config) -> None:
        self.database = database
        self.config = config
        self.running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start the file mover service."""
        self.running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop the file mover service."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self) -> None:
        """Process jobs that are ready to be moved."""
        while self.running:
            moving_jobs = await self.database.get_jobs_by_status(JobStatus.MOVING)
            for job in moving_jobs:
                await self._process_job(job)
            await asyncio.sleep(0.01)

    async def _process_job(self, job: Job) -> None:
        """Process a single file move job."""
        if not job.identified_title or not job.identified_year:
            await self.database.update_job_status(
                job.id, JobStatus.FAILED, "Missing identification"
            )
            return

        # Determine destination based on content type
        if job.content_type == ContentType.MOVIE:
            dest_dir = (
                self.config.plex_movies_dir
                / f"{job.identified_title} ({job.identified_year})"
            )
        else:
            dest_dir = (
                self.config.plex_tv_dir / job.identified_title / f"Season {job.identified_year}"
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        final_path = dest_dir / f"{job.identified_title} ({job.identified_year}).mkv"

        # Simulate file move (just create the destination file)
        final_path.write_bytes(b"final encoded content")

        await self.database.update_job_final_path(job.id, str(final_path))
        await self.database.add_to_collection(
            job.identified_title,
            job.identified_year,
            job.tmdb_id or 0,
            job.content_type,
            str(final_path),
        )
        await self.database.update_job_status(job.id, JobStatus.COMPLETE)


class MockNotifier:
    """Mock notifier that captures notifications."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.notifications: list[dict[str, Any]] = []

    async def send(
        self,
        title: str,
        message: str,
        priority: int = 0,
        url: Optional[str] = None,
    ) -> bool:
        """Send a notification (mock)."""
        self.notifications.append(
            {
                "title": title,
                "message": message,
                "priority": priority,
                "url": url,
            }
        )
        return True

    async def notify_disc_complete(self, disc_label: str, title: str) -> bool:
        """Notify disc rip complete."""
        return await self.send(
            "Disc Complete",
            f"'{disc_label}' identified as '{title}'",
        )

    async def notify_error(self, disc_label: str, error: str) -> bool:
        """Notify error."""
        return await self.send(
            "Rip Error",
            f"Error processing '{disc_label}': {error}",
            priority=1,
        )

    async def notify_review_needed(self, disc_label: str, best_match: str) -> bool:
        """Notify review needed."""
        return await self.send(
            "Review Needed",
            f"'{disc_label}' needs review. Best match: '{best_match}'",
            url="http://localhost:8080/review",
        )


# ============================================================================
# Integration Tests
# ============================================================================


class TestJobStateTransitions:
    """Test job state transitions through the full pipeline lifecycle."""

    @pytest.mark.asyncio
    async def test_full_pipeline_high_confidence(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test complete pipeline with high confidence identification (auto-approve)."""
        # Create services
        drive_watcher = MockDriveWatcher(mock_database, test_config)
        rip_queue = MockRipQueue(mock_database, test_config)
        encode_queue = MockEncodeQueue(mock_database, test_config)
        identifier = MockIdentifierService(mock_database, test_config, default_confidence=0.95)
        file_mover = MockFileMover(mock_database, test_config)

        # Start services
        await rip_queue.start()
        await encode_queue.start()
        await identifier.start()
        await file_mover.start()

        try:
            # Simulate disc insertion
            job_id = await drive_watcher.simulate_disc_insertion("disk0", "THE_MATRIX_1999")

            # Wait for pipeline to complete
            for _ in range(100):  # Timeout after 100 iterations
                job = await mock_database.get_job(job_id)
                if job and job.status == JobStatus.COMPLETE:
                    break
                await asyncio.sleep(0.01)

            # Verify job completed successfully
            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.COMPLETE
            assert job.identified_title is not None
            assert job.final_path is not None
            assert len(mock_database.collection) == 1

        finally:
            # Stop services
            await file_mover.stop()
            await identifier.stop()
            await encode_queue.stop()
            await rip_queue.stop()

    @pytest.mark.asyncio
    async def test_pipeline_low_confidence_review(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test pipeline with low confidence identification (needs review)."""
        # Create services with low confidence
        drive_watcher = MockDriveWatcher(mock_database, test_config)
        rip_queue = MockRipQueue(mock_database, test_config)
        encode_queue = MockEncodeQueue(mock_database, test_config)
        identifier = MockIdentifierService(mock_database, test_config, default_confidence=0.5)
        file_mover = MockFileMover(mock_database, test_config)

        # Start services
        await rip_queue.start()
        await encode_queue.start()
        await identifier.start()
        await file_mover.start()

        try:
            # Simulate disc insertion
            job_id = await drive_watcher.simulate_disc_insertion("disk0", "UNKNOWN_DISC")

            # Wait for job to reach REVIEW status
            for _ in range(100):
                job = await mock_database.get_job(job_id)
                if job and job.status == JobStatus.REVIEW:
                    break
                await asyncio.sleep(0.01)

            # Verify job is in review status
            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.REVIEW
            assert job.confidence is not None
            assert job.confidence < test_config.auto_approve_threshold

            # Simulate manual approval by setting status to MOVING
            await mock_database.update_job_status(job_id, JobStatus.MOVING)

            # Wait for file mover to complete
            for _ in range(100):
                job = await mock_database.get_job(job_id)
                if job and job.status == JobStatus.COMPLETE:
                    break
                await asyncio.sleep(0.01)

            # Verify job completed
            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.COMPLETE

        finally:
            await file_mover.stop()
            await identifier.stop()
            await encode_queue.stop()
            await rip_queue.stop()

    @pytest.mark.asyncio
    async def test_state_transition_pending_to_ripping(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test state transition from PENDING to RIPPING."""
        drive_watcher = MockDriveWatcher(mock_database, test_config)
        rip_queue = MockRipQueue(mock_database, test_config)

        await rip_queue.start()

        try:
            job_id = await drive_watcher.simulate_disc_insertion("disk0", "TEST_DISC")

            # Verify initial state
            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.PENDING

            # Wait for ripping to start
            for _ in range(50):
                job = await mock_database.get_job(job_id)
                if job and job.status in (JobStatus.RIPPING, JobStatus.RIPPED):
                    break
                await asyncio.sleep(0.01)

            # Verify state transition happened
            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status in (JobStatus.RIPPING, JobStatus.RIPPED)

        finally:
            await rip_queue.stop()

    @pytest.mark.asyncio
    async def test_state_transition_ripped_to_encoding(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test state transition from RIPPED to ENCODING."""
        rip_queue = MockRipQueue(mock_database, test_config)
        encode_queue = MockEncodeQueue(mock_database, test_config)

        await rip_queue.start()
        await encode_queue.start()

        try:
            # Create a job directly
            job_id = await mock_database.create_job("disk0", "TEST_DISC")

            # Wait for ripping and encoding
            for _ in range(100):
                job = await mock_database.get_job(job_id)
                if job and job.status == JobStatus.ENCODED:
                    break
                await asyncio.sleep(0.01)

            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.ENCODED
            assert job.rip_path is not None
            assert job.encode_path is not None

        finally:
            await encode_queue.stop()
            await rip_queue.stop()

    @pytest.mark.asyncio
    async def test_state_transition_encoded_to_identifying(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test state transition from ENCODED to IDENTIFYING."""
        rip_queue = MockRipQueue(mock_database, test_config)
        encode_queue = MockEncodeQueue(mock_database, test_config)
        identifier = MockIdentifierService(mock_database, test_config)

        await rip_queue.start()
        await encode_queue.start()
        await identifier.start()

        try:
            job_id = await mock_database.create_job("disk0", "THE_GODFATHER")

            # Wait for identification
            for _ in range(100):
                job = await mock_database.get_job(job_id)
                if job and job.status in (JobStatus.REVIEW, JobStatus.MOVING):
                    break
                await asyncio.sleep(0.01)

            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status in (JobStatus.REVIEW, JobStatus.MOVING)
            assert job.identified_title is not None
            assert job.tmdb_id is not None

        finally:
            await identifier.stop()
            await encode_queue.stop()
            await rip_queue.stop()

    @pytest.mark.asyncio
    async def test_parallel_drive_processing(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test parallel processing of jobs from two drives."""
        drive_watcher = MockDriveWatcher(mock_database, test_config)
        rip_queue = MockRipQueue(mock_database, test_config)

        await rip_queue.start()

        try:
            # Insert discs in both drives simultaneously
            job1_id = await drive_watcher.simulate_disc_insertion("disk0", "MOVIE_A")
            job2_id = await drive_watcher.simulate_disc_insertion("disk1", "MOVIE_B")

            # Wait for both to be ripped
            for _ in range(100):
                job1 = await mock_database.get_job(job1_id)
                job2 = await mock_database.get_job(job2_id)
                if (
                    job1
                    and job2
                    and job1.status == JobStatus.RIPPED
                    and job2.status == JobStatus.RIPPED
                ):
                    break
                await asyncio.sleep(0.01)

            # Both jobs should be ripped
            job1 = await mock_database.get_job(job1_id)
            job2 = await mock_database.get_job(job2_id)

            assert job1 is not None
            assert job2 is not None
            assert job1.status == JobStatus.RIPPED
            assert job2.status == JobStatus.RIPPED
            assert job1.rip_path != job2.rip_path

        finally:
            await rip_queue.stop()

    @pytest.mark.asyncio
    async def test_custom_identification_result(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test with custom identification result preset."""
        identifier = MockIdentifierService(mock_database, test_config)

        # Set up custom identification
        identifier.set_identification(
            "STAR_WARS_1977",
            IdentificationResult(
                content_type=ContentType.MOVIE,
                title="Star Wars: Episode IV - A New Hope",
                year=1977,
                tmdb_id=11,
                confidence=0.98,
                needs_review=False,
                alternatives=[],
            ),
        )

        rip_queue = MockRipQueue(mock_database, test_config)
        encode_queue = MockEncodeQueue(mock_database, test_config)
        file_mover = MockFileMover(mock_database, test_config)

        await rip_queue.start()
        await encode_queue.start()
        await identifier.start()
        await file_mover.start()

        try:
            job_id = await mock_database.create_job("disk0", "STAR_WARS_1977")

            # Wait for completion
            for _ in range(100):
                job = await mock_database.get_job(job_id)
                if job and job.status == JobStatus.COMPLETE:
                    break
                await asyncio.sleep(0.01)

            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.COMPLETE
            assert job.identified_title == "Star Wars: Episode IV - A New Hope"
            assert job.identified_year == 1977
            assert job.tmdb_id == 11

        finally:
            await file_mover.stop()
            await identifier.stop()
            await encode_queue.stop()
            await rip_queue.stop()


class TestConfigFixture:
    """Test the configuration fixture."""

    def test_config_has_temp_directories(self, test_config: Config) -> None:
        """Test that config uses temporary directories."""
        assert test_config.workspace_dir.exists()
        assert test_config.plex_movies_dir.exists()
        assert test_config.plex_tv_dir.exists()

    def test_config_has_test_credentials(self, test_config: Config) -> None:
        """Test that config has test credentials."""
        assert test_config.pushover_user_key == "test_user_key"
        assert test_config.pushover_api_token == "test_api_token"
        assert test_config.tmdb_api_token == "test_tmdb_token"

    def test_config_has_fast_poll_interval(self, test_config: Config) -> None:
        """Test that config has fast poll interval for testing."""
        assert test_config.poll_interval == 0.1


class TestDatabaseFixture:
    """Test the database fixture."""

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

    @pytest.mark.asyncio
    async def test_update_job_status(self, mock_database: MockDatabase) -> None:
        """Test updating job status."""
        job_id = await mock_database.create_job("disk0", "TEST_DISC")
        await mock_database.update_job_status(job_id, JobStatus.RIPPING)

        job = await mock_database.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.RIPPING

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


class TestErrorHandling:
    """Test error handling in the pipeline."""

    @pytest.mark.asyncio
    async def test_failed_job_status(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test that jobs can be marked as failed with error message."""
        job_id = await mock_database.create_job("disk0", "BAD_DISC")
        await mock_database.update_job_status(
            job_id, JobStatus.FAILED, "Disc read error"
        )

        job = await mock_database.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert job.error_message == "Disc read error"

    @pytest.mark.asyncio
    async def test_file_mover_missing_identification(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test file mover handles missing identification."""
        file_mover = MockFileMover(mock_database, test_config)
        await file_mover.start()

        try:
            # Create a job and set it to MOVING without identification
            job_id = await mock_database.create_job("disk0", "TEST_DISC")
            await mock_database.update_job_status(job_id, JobStatus.MOVING)

            # Wait for file mover to process
            for _ in range(50):
                job = await mock_database.get_job(job_id)
                if job and job.status == JobStatus.FAILED:
                    break
                await asyncio.sleep(0.01)

            job = await mock_database.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.FAILED
            assert job.error_message == "Missing identification"

        finally:
            await file_mover.stop()


class TestNotifications:
    """Test notification integration."""

    @pytest.mark.asyncio
    async def test_notification_on_disc_complete(
        self, test_config: Config
    ) -> None:
        """Test notification sent on disc complete."""
        notifier = MockNotifier(test_config)
        await notifier.notify_disc_complete("THE_MATRIX", "The Matrix (1999)")

        assert len(notifier.notifications) == 1
        assert "Disc Complete" in notifier.notifications[0]["title"]
        assert "The Matrix" in notifier.notifications[0]["message"]

    @pytest.mark.asyncio
    async def test_notification_on_error(self, test_config: Config) -> None:
        """Test notification sent on error."""
        notifier = MockNotifier(test_config)
        await notifier.notify_error("BAD_DISC", "Unreadable disc")

        assert len(notifier.notifications) == 1
        assert "Error" in notifier.notifications[0]["title"]
        assert notifier.notifications[0]["priority"] == 1

    @pytest.mark.asyncio
    async def test_notification_on_review_needed(
        self, test_config: Config
    ) -> None:
        """Test notification sent when review is needed."""
        notifier = MockNotifier(test_config)
        await notifier.notify_review_needed("UNKNOWN_DISC", "Possible Match (2020)")

        assert len(notifier.notifications) == 1
        assert "Review" in notifier.notifications[0]["title"]
        assert notifier.notifications[0]["url"] is not None


class TestCollectionTracking:
    """Test collection tracking functionality."""

    @pytest.mark.asyncio
    async def test_add_to_collection_on_complete(
        self, test_config: Config, mock_database: MockDatabase
    ) -> None:
        """Test that completed jobs are added to collection."""
        rip_queue = MockRipQueue(mock_database, test_config)
        encode_queue = MockEncodeQueue(mock_database, test_config)
        identifier = MockIdentifierService(mock_database, test_config, default_confidence=0.95)
        file_mover = MockFileMover(mock_database, test_config)

        await rip_queue.start()
        await encode_queue.start()
        await identifier.start()
        await file_mover.start()

        try:
            job_id = await mock_database.create_job("disk0", "INCEPTION_2010")

            # Wait for completion
            for _ in range(100):
                job = await mock_database.get_job(job_id)
                if job and job.status == JobStatus.COMPLETE:
                    break
                await asyncio.sleep(0.01)

            # Verify collection was updated
            assert len(mock_database.collection) == 1
            assert mock_database.collection[0]["title"] is not None

        finally:
            await file_mover.stop()
            await identifier.stop()
            await encode_queue.stop()
            await rip_queue.stop()


# ============================================================================
# Main entry point for running tests directly
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
