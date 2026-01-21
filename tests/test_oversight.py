"""Tests for the oversight service."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from dvdtoplex.database import Database, JobStatus
from dvdtoplex.services.oversight import (
    RIPPING_TIMEOUT_HOURS,
    ENCODING_TIMEOUT_HOURS,
    IDENTIFYING_TIMEOUT_HOURS,
    check_state_consistency,
    fix_stuck_encoding_jobs,
    startup_cleanup,
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


async def set_job_updated_at(db: Database, job_id: int, hours_ago: float) -> None:
    """Helper to set a job's updated_at to a specific time in the past."""
    past_time = datetime.now() - timedelta(hours=hours_ago)
    await db.connection.execute(
        "UPDATE jobs SET updated_at = ? WHERE id = ?",
        (past_time.isoformat(), job_id),
    )
    await db.connection.commit()


class TestCheckMultipleEncodingJobs:
    """Tests for detecting multiple ENCODING jobs."""

    @pytest.mark.asyncio
    async def test_check_multiple_encoding_jobs(self, db: Database) -> None:
        """Detects when 2+ jobs are in ENCODING status."""
        # Create two jobs and set both to ENCODING
        job1 = await db.create_job("drive0", "DISC1")
        job2 = await db.create_job("drive1", "DISC2")
        await db.update_job_status(job1.id, JobStatus.ENCODING)
        await db.update_job_status(job2.id, JobStatus.ENCODING)

        issues = await check_state_consistency(db)

        assert len(issues) == 1
        assert "Multiple jobs in ENCODING status" in issues[0]
        assert "2" in issues[0]  # Should mention count

    @pytest.mark.asyncio
    async def test_single_encoding_job_is_ok(self, db: Database) -> None:
        """Single ENCODING job should not be flagged."""
        job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(job.id, JobStatus.ENCODING)

        issues = await check_state_consistency(db)

        # No issues about multiple encoding jobs
        assert not any("Multiple jobs in ENCODING" in issue for issue in issues)


class TestCheckMultipleRippingOnSameDrive:
    """Tests for detecting multiple RIPPING jobs on same drive."""

    @pytest.mark.asyncio
    async def test_check_multiple_ripping_same_drive(self, db: Database) -> None:
        """Detects when 2+ jobs are RIPPING on the same drive."""
        job1 = await db.create_job("drive0", "DISC1")
        job2 = await db.create_job("drive0", "DISC2")
        await db.update_job_status(job1.id, JobStatus.RIPPING)
        await db.update_job_status(job2.id, JobStatus.RIPPING)

        issues = await check_state_consistency(db)

        assert len(issues) == 1
        assert "Multiple jobs RIPPING on drive" in issues[0]
        assert "drive0" in issues[0]

    @pytest.mark.asyncio
    async def test_ripping_on_different_drives_is_ok(self, db: Database) -> None:
        """RIPPING on different drives should not be flagged."""
        job1 = await db.create_job("drive0", "DISC1")
        job2 = await db.create_job("drive1", "DISC2")
        await db.update_job_status(job1.id, JobStatus.RIPPING)
        await db.update_job_status(job2.id, JobStatus.RIPPING)

        issues = await check_state_consistency(db)

        # No issues about multiple ripping on same drive
        assert not any("Multiple jobs RIPPING on drive" in issue for issue in issues)


class TestCheckStuckJobs:
    """Tests for detecting jobs stuck in transient states."""

    @pytest.mark.asyncio
    async def test_check_stuck_encoding_job(self, db: Database) -> None:
        """Detects job stuck in ENCODING for >8 hours."""
        job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(job.id, JobStatus.ENCODING)
        # Set updated_at to 9 hours ago
        await set_job_updated_at(db, job.id, ENCODING_TIMEOUT_HOURS + 1)

        issues = await check_state_consistency(db)

        assert len(issues) == 1
        assert "stuck" in issues[0].lower()
        assert "ENCODING" in issues[0]
        assert str(job.id) in issues[0]

    @pytest.mark.asyncio
    async def test_check_stuck_ripping_job(self, db: Database) -> None:
        """Detects job stuck in RIPPING for >4 hours."""
        job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(job.id, JobStatus.RIPPING)
        # Set updated_at to 5 hours ago
        await set_job_updated_at(db, job.id, RIPPING_TIMEOUT_HOURS + 1)

        issues = await check_state_consistency(db)

        assert len(issues) == 1
        assert "stuck" in issues[0].lower()
        assert "RIPPING" in issues[0]

    @pytest.mark.asyncio
    async def test_check_stuck_identifying_job(self, db: Database) -> None:
        """Detects job stuck in IDENTIFYING for >1 hour."""
        job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(job.id, JobStatus.IDENTIFYING)
        # Set updated_at to 2 hours ago
        await set_job_updated_at(db, job.id, IDENTIFYING_TIMEOUT_HOURS + 1)

        issues = await check_state_consistency(db)

        assert len(issues) == 1
        assert "stuck" in issues[0].lower()
        assert "IDENTIFYING" in issues[0]

    @pytest.mark.asyncio
    async def test_recent_encoding_job_is_ok(self, db: Database) -> None:
        """ENCODING job that started recently should not be flagged."""
        job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(job.id, JobStatus.ENCODING)
        # Leave updated_at as recent

        issues = await check_state_consistency(db)

        # No issues about stuck jobs
        assert not any("stuck" in issue.lower() for issue in issues)


class TestNoIssuesNormalState:
    """Tests for normal/valid states."""

    @pytest.mark.asyncio
    async def test_no_issues_normal_state(self, db: Database) -> None:
        """Returns empty list for valid state."""
        # Create various jobs in valid states
        job1 = await db.create_job("drive0", "DISC1")
        job2 = await db.create_job("drive1", "DISC2")
        job3 = await db.create_job("drive0", "DISC3")

        # One pending, one ripping, one complete - all valid
        await db.update_job_status(job2.id, JobStatus.RIPPING)
        await db.update_job_status(job3.id, JobStatus.COMPLETE)

        issues = await check_state_consistency(db)

        assert issues == []

    @pytest.mark.asyncio
    async def test_no_issues_empty_database(self, db: Database) -> None:
        """Returns empty list when no jobs exist."""
        issues = await check_state_consistency(db)
        assert issues == []

    @pytest.mark.asyncio
    async def test_completed_jobs_not_checked(self, db: Database) -> None:
        """COMPLETE/FAILED/ARCHIVED jobs should not be checked for issues."""
        job1 = await db.create_job("drive0", "DISC1")
        job2 = await db.create_job("drive1", "DISC2")
        job3 = await db.create_job("drive2", "DISC3")

        await db.update_job_status(job1.id, JobStatus.COMPLETE)
        await db.update_job_status(job2.id, JobStatus.FAILED)
        await db.update_job_status(job3.id, JobStatus.ARCHIVED)

        # Set old timestamps - these should be ignored
        await set_job_updated_at(db, job1.id, 100)
        await set_job_updated_at(db, job2.id, 100)
        await set_job_updated_at(db, job3.id, 100)

        issues = await check_state_consistency(db)

        assert issues == []


class TestFixStuckEncodingJobs:
    """Tests for fix_stuck_encoding_jobs function."""

    @pytest.mark.asyncio
    async def test_fix_resets_all_but_most_recent(self, db: Database) -> None:
        """Resets all but the most recent ENCODING job to RIPPED."""
        job1 = await db.create_job("drive0", "DISC1")
        job2 = await db.create_job("drive1", "DISC2")
        job3 = await db.create_job("drive2", "DISC3")

        await db.update_job_status(job1.id, JobStatus.ENCODING)
        await db.update_job_status(job2.id, JobStatus.ENCODING)
        await db.update_job_status(job3.id, JobStatus.ENCODING)

        # Make job3 the most recent
        await set_job_updated_at(db, job1.id, 3)
        await set_job_updated_at(db, job2.id, 2)
        # job3 keeps recent timestamp

        count = await fix_stuck_encoding_jobs(db)

        assert count == 2

        # Check job statuses
        updated_job1 = await db.get_job(job1.id)
        updated_job2 = await db.get_job(job2.id)
        updated_job3 = await db.get_job(job3.id)

        assert updated_job1 is not None
        assert updated_job2 is not None
        assert updated_job3 is not None

        assert updated_job1.status == JobStatus.RIPPED
        assert updated_job2.status == JobStatus.RIPPED
        assert updated_job3.status == JobStatus.ENCODING  # Most recent kept

    @pytest.mark.asyncio
    async def test_fix_single_encoding_job_no_change(self, db: Database) -> None:
        """Single ENCODING job should not be changed."""
        job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(job.id, JobStatus.ENCODING)

        count = await fix_stuck_encoding_jobs(db)

        assert count == 0

        updated_job = await db.get_job(job.id)
        assert updated_job is not None
        assert updated_job.status == JobStatus.ENCODING

    @pytest.mark.asyncio
    async def test_fix_no_encoding_jobs(self, db: Database) -> None:
        """No ENCODING jobs should return 0."""
        job = await db.create_job("drive0", "DISC1")
        await db.update_job_status(job.id, JobStatus.RIPPED)

        count = await fix_stuck_encoding_jobs(db)

        assert count == 0


class TestTimeoutConstants:
    """Tests for timeout constant values."""

    def test_ripping_timeout_is_4_hours(self) -> None:
        """RIPPING timeout should be 4 hours."""
        assert RIPPING_TIMEOUT_HOURS == 4

    def test_encoding_timeout_is_8_hours(self) -> None:
        """ENCODING timeout should be 8 hours."""
        assert ENCODING_TIMEOUT_HOURS == 8

    def test_identifying_timeout_is_1_hour(self) -> None:
        """IDENTIFYING timeout should be 1 hour."""
        assert IDENTIFYING_TIMEOUT_HOURS == 1


class TestStartupCleanup:
    """Tests for startup_cleanup function."""

    @pytest.mark.asyncio
    async def test_startup_cleanup_resets_ripping(self) -> None:
        """Startup should reset RIPPING jobs to FAILED."""
        from dvdtoplex.database import Job

        job = Job(
            id=1, drive_id="1", disc_label="DISC", content_type=None, status=JobStatus.RIPPING,
            identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
            poster_path=None, rip_path=None, encode_path=None, final_path=None,
            error_message=None, created_at=datetime.now(), updated_at=datetime.now()
        )

        mock_db = AsyncMock()
        mock_db.get_all_jobs.return_value = [job]

        results = await startup_cleanup(mock_db)

        assert results["reset_ripping"] == 1
        mock_db.update_job_status.assert_called_once()
        call_args = mock_db.update_job_status.call_args
        assert call_args[0][0] == 1
        assert call_args[0][1] == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_startup_cleanup_resets_encoding(self) -> None:
        """Startup should reset ENCODING jobs to RIPPED."""
        from dvdtoplex.database import Job

        job = Job(
            id=1, drive_id="1", disc_label="DISC", content_type=None, status=JobStatus.ENCODING,
            identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
            poster_path=None, rip_path=None, encode_path=None, final_path=None,
            error_message=None, created_at=datetime.now(), updated_at=datetime.now()
        )

        mock_db = AsyncMock()
        mock_db.get_all_jobs.return_value = [job]

        results = await startup_cleanup(mock_db)

        assert results["reset_encoding"] == 1
        mock_db.update_job_status.assert_called_once_with(1, JobStatus.RIPPED)

    @pytest.mark.asyncio
    async def test_startup_cleanup_resets_identifying(self) -> None:
        """Startup should reset IDENTIFYING jobs to ENCODED."""
        from dvdtoplex.database import Job

        job = Job(
            id=1, drive_id="1", disc_label="DISC", content_type=None, status=JobStatus.IDENTIFYING,
            identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
            poster_path=None, rip_path=None, encode_path=None, final_path=None,
            error_message=None, created_at=datetime.now(), updated_at=datetime.now()
        )

        mock_db = AsyncMock()
        mock_db.get_all_jobs.return_value = [job]

        results = await startup_cleanup(mock_db)

        assert results["reset_identifying"] == 1
        mock_db.update_job_status.assert_called_once_with(1, JobStatus.ENCODED)

    @pytest.mark.asyncio
    async def test_startup_cleanup_ignores_other_statuses(self) -> None:
        """Startup should not touch jobs in other statuses."""
        from dvdtoplex.database import Job

        jobs = [
            Job(
                id=1, drive_id="1", disc_label="DISC1", content_type=None, status=JobStatus.PENDING,
                identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
                poster_path=None, rip_path=None, encode_path=None, final_path=None,
                error_message=None, created_at=datetime.now(), updated_at=datetime.now()
            ),
            Job(
                id=2, drive_id="1", disc_label="DISC2", content_type=None, status=JobStatus.COMPLETE,
                identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
                poster_path=None, rip_path=None, encode_path=None, final_path=None,
                error_message=None, created_at=datetime.now(), updated_at=datetime.now()
            ),
            Job(
                id=3, drive_id="1", disc_label="DISC3", content_type=None, status=JobStatus.FAILED,
                identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
                poster_path=None, rip_path=None, encode_path=None, final_path=None,
                error_message=None, created_at=datetime.now(), updated_at=datetime.now()
            ),
        ]

        mock_db = AsyncMock()
        mock_db.get_all_jobs.return_value = jobs

        results = await startup_cleanup(mock_db)

        assert results["reset_ripping"] == 0
        assert results["reset_encoding"] == 0
        assert results["reset_identifying"] == 0
        mock_db.update_job_status.assert_not_called()
