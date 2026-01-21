"""Tests for the skip job endpoint."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from dvdtoplex.web.app import create_app
from dvdtoplex.database import JobStatus


@pytest.fixture
def client():
    """Create a test client for the app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def app_with_review_job():
    """Create an app with a job in review status."""
    app = create_app()
    app.state.jobs = [
        {
            "id": 1,
            "disc_label": "TEST_DISC_1",
            "status": "review",
            "confidence": 0.65,
            "identified_title": "Test Movie",
            "identified_year": 2024,
            "content_type": "movie",
        }
    ]
    return app


@pytest.fixture
def client_with_job(app_with_review_job):
    """Create a test client with a job in review status."""
    return TestClient(app_with_review_job)


class TestSkipEndpoint:
    """Tests for POST /api/jobs/{job_id}/skip endpoint."""

    def test_skip_job_success(self, client_with_job, app_with_review_job):
        """Test successfully skipping a job in review status."""
        response = client_with_job.post("/api/jobs/1/skip")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == 1
        assert data["status"] == "failed"
        assert data["error_message"] == "Skipped by user"

        # Verify job was updated in state
        job = app_with_review_job.state.jobs[0]
        assert job["status"] == "failed"
        assert job["error_message"] == "Skipped by user"

    def test_skip_job_not_found(self, client):
        """Test skipping a non-existent job returns 404."""
        response = client.post("/api/jobs/999/skip")

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Job not found"

    def test_skip_job_not_in_review_status(self, client):
        """Test skipping a job not in review status returns 400."""
        app = create_app()
        app.state.jobs = [
            {
                "id": 1,
                "disc_label": "TEST_DISC_1",
                "status": "encoding",  # Not in review
            }
        ]
        test_client = TestClient(app)

        response = test_client.post("/api/jobs/1/skip")

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "not in review status" in data["error"]

    def test_skip_job_already_complete(self, client):
        """Test skipping an already complete job returns 400."""
        app = create_app()
        app.state.jobs = [
            {
                "id": 1,
                "disc_label": "TEST_DISC_1",
                "status": "complete",
            }
        ]
        test_client = TestClient(app)

        response = test_client.post("/api/jobs/1/skip")

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False

    def test_skip_job_already_failed(self, client):
        """Test skipping an already failed job returns 400."""
        app = create_app()
        app.state.jobs = [
            {
                "id": 1,
                "disc_label": "TEST_DISC_1",
                "status": "failed",
                "error_message": "Previous error",
            }
        ]
        test_client = TestClient(app)

        response = test_client.post("/api/jobs/1/skip")

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False

    def test_skip_multiple_jobs(self, client):
        """Test skipping multiple jobs works correctly."""
        app = create_app()
        app.state.jobs = [
            {"id": 1, "disc_label": "DISC_1", "status": "review"},
            {"id": 2, "disc_label": "DISC_2", "status": "review"},
            {"id": 3, "disc_label": "DISC_3", "status": "review"},
        ]
        test_client = TestClient(app)

        # Skip job 2
        response = test_client.post("/api/jobs/2/skip")
        assert response.status_code == 200
        assert app.state.jobs[1]["status"] == "failed"

        # Job 1 and 3 should still be in review
        assert app.state.jobs[0]["status"] == "review"
        assert app.state.jobs[2]["status"] == "review"

        # Skip job 1
        response = test_client.post("/api/jobs/1/skip")
        assert response.status_code == 200
        assert app.state.jobs[0]["status"] == "failed"


class TestSkipEndpointWithDatabase:
    """Tests for skip endpoint with database."""

    @pytest.mark.asyncio
    async def test_skip_job_with_database(self):
        """Test skip endpoint uses database when available."""
        # Create mock database
        mock_db = AsyncMock()
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.status = JobStatus.REVIEW
        mock_db.get_job.return_value = mock_job
        mock_db.update_job_status.return_value = None

        app = create_app(database=mock_db)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/jobs/1/skip")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "failed"
        mock_db.get_job.assert_called_once_with(1)
        mock_db.update_job_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_job_not_found_with_database(self):
        """Test skip returns 404 when job not in database."""
        mock_db = AsyncMock()
        mock_db.get_job.return_value = None

        app = create_app(database=mock_db)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/jobs/999/skip")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_skip_job_wrong_status_with_database(self):
        """Test skip returns 400 when job not in REVIEW status."""
        mock_db = AsyncMock()
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.status = JobStatus.COMPLETE
        mock_db.get_job.return_value = mock_job

        app = create_app(database=mock_db)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/jobs/1/skip")

        assert response.status_code == 400
