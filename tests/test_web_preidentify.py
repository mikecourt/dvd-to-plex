"""Tests for the POST /api/jobs/{job_id}/pre-identify endpoint."""

import pytest
from fastapi.testclient import TestClient

from dvdtoplex.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_pending_job(client: TestClient) -> TestClient:
    """Create a test client with a job in pending status."""
    app = client.app
    app.state.jobs = [
        {
            "id": 1,
            "disc_label": "MY_MOVIE_DISC",
            "status": "pending",
            "identified_title": None,
            "identified_year": None,
            "tmdb_id": None,
            "confidence": None,
        }
    ]
    return client


@pytest.fixture
def client_with_ripping_job(client: TestClient) -> TestClient:
    """Create a test client with a job in ripping status."""
    app = client.app
    app.state.jobs = [
        {
            "id": 1,
            "disc_label": "MY_MOVIE_DISC",
            "status": "ripping",
            "identified_title": None,
            "identified_year": None,
            "tmdb_id": None,
            "confidence": None,
        }
    ]
    return client


@pytest.fixture
def client_with_review_job(client: TestClient) -> TestClient:
    """Create a test client with a job in review status."""
    app = client.app
    app.state.jobs = [
        {
            "id": 1,
            "disc_label": "MY_MOVIE_DISC",
            "status": "review",
            "identified_title": "Unknown Movie",
            "identified_year": None,
            "tmdb_id": None,
            "confidence": 0.5,
        }
    ]
    return client


@pytest.fixture
def client_with_complete_job(client: TestClient) -> TestClient:
    """Create a test client with a job in complete status."""
    app = client.app
    app.state.jobs = [
        {
            "id": 1,
            "disc_label": "MY_MOVIE_DISC",
            "status": "complete",
            "identified_title": "Some Movie",
            "identified_year": 2020,
            "tmdb_id": 12345,
            "confidence": 1.0,
        }
    ]
    return client


class TestPreIdentifyEndpoint:
    """Tests for POST /api/jobs/{job_id}/pre-identify endpoint."""

    def test_preidentify_job_success(self, client_with_pending_job: TestClient) -> None:
        """Test pre-identifying a job sets title/year but does NOT change status."""
        # Verify initial status
        job = client_with_pending_job.app.state.jobs[0]
        assert job["status"] == "pending"
        assert job["identified_title"] is None

        # Pre-identify the job
        response = client_with_pending_job.post(
            "/api/jobs/1/pre-identify",
            json={"title": "The Matrix", "year": 1999},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == 1
        assert data["identified_title"] == "The Matrix"
        assert data["identified_year"] == 1999

        # Verify job state was updated - title/year set, but status unchanged
        job = client_with_pending_job.app.state.jobs[0]
        assert job["status"] == "pending"  # Status should NOT change
        assert job["identified_title"] == "The Matrix"
        assert job["identified_year"] == 1999

    def test_preidentify_job_ripping_status(self, client_with_ripping_job: TestClient) -> None:
        """Test pre-identifying a job in ripping status works."""
        response = client_with_ripping_job.post(
            "/api/jobs/1/pre-identify",
            json={"title": "Inception", "year": 2010},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify status unchanged
        job = client_with_ripping_job.app.state.jobs[0]
        assert job["status"] == "ripping"
        assert job["identified_title"] == "Inception"

    def test_preidentify_not_allowed_for_review(self, client_with_review_job: TestClient) -> None:
        """Test that pre-identify returns 400 for jobs in REVIEW status."""
        response = client_with_review_job.post(
            "/api/jobs/1/pre-identify",
            json={"title": "The Matrix", "year": 1999},
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data or "error" in data
        # Check that the error mentions the status restriction
        error_msg = data.get("detail", data.get("error", ""))
        assert "review" in error_msg.lower() or "not allowed" in error_msg.lower()

    def test_preidentify_not_allowed_for_complete(self, client_with_complete_job: TestClient) -> None:
        """Test that pre-identify returns 400 for jobs in COMPLETE status."""
        response = client_with_complete_job.post(
            "/api/jobs/1/pre-identify",
            json={"title": "The Matrix", "year": 1999},
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data or "error" in data

    def test_preidentify_job_not_found(self, client: TestClient) -> None:
        """Test pre-identifying a non-existent job returns 404."""
        response = client.post(
            "/api/jobs/999/pre-identify",
            json={"title": "The Matrix"},
        )
        assert response.status_code == 404
        data = response.json()
        assert data.get("success") is False or "error" in data or "detail" in data

    def test_preidentify_job_missing_title(self, client_with_pending_job: TestClient) -> None:
        """Test that title is required."""
        response = client_with_pending_job.post(
            "/api/jobs/1/pre-identify",
            json={},
        )
        assert response.status_code == 422  # Validation error
