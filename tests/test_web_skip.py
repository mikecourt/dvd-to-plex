"""Tests for the POST /api/jobs/{job_id}/skip endpoint."""

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


class TestSkipEndpoint:
    """Tests for POST /api/jobs/{job_id}/skip endpoint."""

    def test_skip_job_success(self, client_with_review_job: TestClient) -> None:
        """Test successfully skipping a job in REVIEW status."""
        response = client_with_review_job.post("/api/jobs/1/skip")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == 1
        assert data["status"] == "failed"
        assert data["error_message"] == "Skipped by user"

    def test_skip_job_not_found(self, client: TestClient) -> None:
        """Test skipping a non-existent job returns 404."""
        response = client.post("/api/jobs/999/skip")
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Job not found"

    def test_skip_job_not_in_review(self, client: TestClient) -> None:
        """Test skipping a job not in review status returns 400."""
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
        response = client.post("/api/jobs/1/skip")
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "not in review status" in data["error"]

    def test_skip_job_transitions_status(self, client_with_review_job: TestClient) -> None:
        """Test that the job transitions from review to failed status."""
        # Verify initial status
        job = client_with_review_job.app.state.jobs[0]
        assert job["status"] == "review"

        # Skip the job
        response = client_with_review_job.post("/api/jobs/1/skip")
        assert response.status_code == 200

        # Verify status changed
        job = client_with_review_job.app.state.jobs[0]
        assert job["status"] == "failed"

    def test_skip_job_sets_error_message(self, client_with_review_job: TestClient) -> None:
        """Test that skipping sets the error_message field."""
        # Skip the job
        response = client_with_review_job.post("/api/jobs/1/skip")
        assert response.status_code == 200

        # Verify error_message is set
        job = client_with_review_job.app.state.jobs[0]
        assert job["error_message"] == "Skipped by user"

    def test_skip_job_with_different_statuses(self, client: TestClient) -> None:
        """Test that skip fails for various non-review statuses."""
        non_review_statuses = ["pending", "ripping", "encoding", "moving", "complete", "failed"]

        for status in non_review_statuses:
            client.app.state.jobs = [
                {
                    "id": 1,
                    "disc_label": "TEST_DISC",
                    "status": status,
                }
            ]
            response = client.post("/api/jobs/1/skip")
            assert response.status_code == 400, f"Expected 400 for status '{status}'"
            data = response.json()
            assert "not in review status" in data["error"]

    def test_skip_job_preserves_other_fields(self, client_with_review_job: TestClient) -> None:
        """Test that skipping preserves other job fields."""
        # Get original job data
        original_job = client_with_review_job.app.state.jobs[0].copy()

        # Skip the job
        response = client_with_review_job.post("/api/jobs/1/skip")
        assert response.status_code == 200

        # Verify other fields are preserved
        job = client_with_review_job.app.state.jobs[0]
        assert job["id"] == original_job["id"]
        assert job["disc_label"] == original_job["disc_label"]
        assert job["identified_title"] == original_job["identified_title"]
        assert job["confidence"] == original_job["confidence"]
