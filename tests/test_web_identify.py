"""Tests for the POST /api/jobs/{job_id}/identify endpoint."""

import pytest
from fastapi.testclient import TestClient

from dvdtoplex.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_review_job(client: TestClient) -> TestClient:
    """Create a test client with a job in review status."""
    # Add a job in review status to the app state
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


class TestIdentifyEndpoint:
    """Tests for POST /api/jobs/{job_id}/identify endpoint."""

    def test_identify_job_with_title_only(self, client_with_review_job: TestClient) -> None:
        """Test identifying a job with just a title."""
        response = client_with_review_job.post(
            "/api/jobs/1/identify",
            json={"title": "The Matrix"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == 1
        assert data["status"] == "moving"
        assert data["identified_title"] == "The Matrix"

    def test_identify_job_with_title_and_year(self, client_with_review_job: TestClient) -> None:
        """Test identifying a job with title and year."""
        response = client_with_review_job.post(
            "/api/jobs/1/identify",
            json={"title": "The Matrix", "year": 1999},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == 1
        assert data["status"] == "moving"
        assert data["identified_title"] == "The Matrix"
        assert data["identified_year"] == 1999

    def test_identify_job_with_all_fields(self, client_with_review_job: TestClient) -> None:
        """Test identifying a job with title, year, and TMDb ID."""
        response = client_with_review_job.post(
            "/api/jobs/1/identify",
            json={"title": "The Matrix", "year": 1999, "tmdb_id": 603},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == 1
        assert data["status"] == "moving"
        assert data["identified_title"] == "The Matrix"
        assert data["identified_year"] == 1999
        assert data["tmdb_id"] == 603

    def test_identify_job_not_found(self, client: TestClient) -> None:
        """Test identifying a non-existent job returns 404."""
        response = client.post(
            "/api/jobs/999/identify",
            json={"title": "The Matrix"},
        )
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Job not found"

    def test_identify_job_not_in_review(self, client: TestClient) -> None:
        """Test identifying a job not in review status returns 400."""
        # Add a job in a different status
        client.app.state.jobs = [
            {
                "id": 1,
                "disc_label": "MY_MOVIE_DISC",
                "status": "encoding",
                "identified_title": None,
                "identified_year": None,
                "tmdb_id": None,
            }
        ]
        response = client.post(
            "/api/jobs/1/identify",
            json={"title": "The Matrix"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "not in review status" in data["error"]

    def test_identify_job_missing_title(self, client_with_review_job: TestClient) -> None:
        """Test that title is required."""
        response = client_with_review_job.post(
            "/api/jobs/1/identify",
            json={},
        )
        assert response.status_code == 422  # Validation error

    def test_identify_job_transitions_status(self, client_with_review_job: TestClient) -> None:
        """Test that the job transitions from review to moving status."""
        # Verify initial status
        job = client_with_review_job.app.state.jobs[0]
        assert job["status"] == "review"

        # Identify the job
        response = client_with_review_job.post(
            "/api/jobs/1/identify",
            json={"title": "The Matrix", "year": 1999},
        )
        assert response.status_code == 200

        # Verify status changed
        job = client_with_review_job.app.state.jobs[0]
        assert job["status"] == "moving"
        assert job["identified_title"] == "The Matrix"
        assert job["identified_year"] == 1999

    def test_identify_job_preserves_existing_year_if_not_provided(
        self, client: TestClient
    ) -> None:
        """Test that existing year is preserved if not provided in request."""
        client.app.state.jobs = [
            {
                "id": 1,
                "disc_label": "MY_MOVIE_DISC",
                "status": "review",
                "identified_title": "Unknown Movie",
                "identified_year": 2000,
                "tmdb_id": None,
            }
        ]
        response = client.post(
            "/api/jobs/1/identify",
            json={"title": "The Matrix"},  # No year provided
        )
        assert response.status_code == 200
        job = client.app.state.jobs[0]
        # Year should be preserved from original
        assert job["identified_year"] == 2000
