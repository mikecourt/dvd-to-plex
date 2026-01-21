"""Tests for the POST /api/jobs/{job_id}/approve endpoint."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from dvdtoplex.database import Database, JobStatus
from dvdtoplex.web.app import create_app


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> Database:
    """Create a test database."""
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def job_in_review(db: Database) -> int:
    """Create a job in REVIEW status and return its ID."""
    cursor = await db.connection.execute(
        """
        INSERT INTO jobs (drive_id, disc_label, status, identified_title, identified_year, tmdb_id, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("drive0", "TEST_DISC", JobStatus.REVIEW.value, "Test Movie", 2023, 12345, 0.75),
    )
    await db.connection.commit()
    return cursor.lastrowid  # type: ignore[return-value]


@pytest_asyncio.fixture
async def job_in_pending(db: Database) -> int:
    """Create a job in PENDING status and return its ID."""
    cursor = await db.connection.execute(
        """
        INSERT INTO jobs (drive_id, disc_label, status)
        VALUES (?, ?, ?)
        """,
        ("drive0", "ANOTHER_DISC", JobStatus.PENDING.value),
    )
    await db.connection.commit()
    return cursor.lastrowid  # type: ignore[return-value]


@pytest.fixture
def client(db: Database) -> TestClient:
    """Create a test client with the FastAPI app."""
    mock_drive_watcher = MagicMock()
    mock_config = MagicMock()
    app = create_app(database=db, drive_watcher=mock_drive_watcher, config=mock_config)
    return TestClient(app)


class TestApproveEndpoint:
    """Tests for POST /api/jobs/{job_id}/approve endpoint."""

    @pytest.mark.asyncio
    async def test_approve_job_success(
        self, client: TestClient, job_in_review: int, db: Database
    ) -> None:
        """Test successfully approving a job in REVIEW status."""
        response = client.post(f"/api/jobs/{job_in_review}/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == job_in_review
        assert data["status"] == "moving"

        # Verify the job status was updated in the database
        job = await db.get_job(job_in_review)
        assert job is not None
        assert job["status"] == JobStatus.MOVING.value

    @pytest.mark.asyncio
    async def test_approve_job_not_found(self, client: TestClient) -> None:
        """Test approving a non-existent job returns 404."""
        response = client.post("/api/jobs/99999/approve")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Job not found"

    @pytest.mark.asyncio
    async def test_approve_job_wrong_status(
        self, client: TestClient, job_in_pending: int
    ) -> None:
        """Test approving a job not in REVIEW status returns 400."""
        response = client.post(f"/api/jobs/{job_in_pending}/approve")

        assert response.status_code == 400
        data = response.json()
        assert "not in REVIEW status" in data["detail"]
        assert "pending" in data["detail"]

    @pytest.mark.asyncio
    async def test_approve_job_preserves_identification(
        self, client: TestClient, job_in_review: int, db: Database
    ) -> None:
        """Test that approving preserves the identification data."""
        # Get original identification
        job_before = await db.get_job(job_in_review)
        assert job_before is not None

        response = client.post(f"/api/jobs/{job_in_review}/approve")
        assert response.status_code == 200

        # Verify identification data is preserved
        job_after = await db.get_job(job_in_review)
        assert job_after is not None
        assert job_after["identified_title"] == job_before["identified_title"]
        assert job_after["identified_year"] == job_before["identified_year"]
        assert job_after["tmdb_id"] == job_before["tmdb_id"]
        assert job_after["confidence"] == job_before["confidence"]
