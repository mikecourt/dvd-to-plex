"""Tests for the web application."""

import pytest
from fastapi.testclient import TestClient

from dvdtoplex.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the web application."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_review_job(client: TestClient) -> TestClient:
    """Create a client with a job in review status."""
    # Add a job in review status
    client.app.state.jobs.append({
        "id": 1,
        "drive_id": "drive0",
        "disc_label": "TEST_MOVIE_DISC",
        "content_type": "movie",
        "status": "review",
        "identified_title": "Test Movie",
        "identified_year": 2024,
        "tmdb_id": 12345,
        "confidence": 0.75,
    })
    return client


class TestApproveEndpoint:
    """Tests for the POST /api/jobs/{job_id}/approve endpoint."""

    def test_approve_job_success(self, client_with_review_job: TestClient) -> None:
        """Test successfully approving a job in review status."""
        response = client_with_review_job.post("/api/jobs/1/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == 1
        assert data["status"] == "moving"
        assert data["identified_title"] == "Test Movie"
        assert data["identified_year"] == 2024

        # Verify job status was updated
        job = client_with_review_job.app.state.jobs[0]
        assert job["status"] == "moving"

    def test_approve_job_not_found(self, client: TestClient) -> None:
        """Test approving a non-existent job returns 404."""
        response = client.post("/api/jobs/999/approve")

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_approve_job_wrong_status(self, client: TestClient) -> None:
        """Test approving a job not in review status returns 400."""
        # Add a job in a different status
        client.app.state.jobs.append({
            "id": 2,
            "drive_id": "drive0",
            "disc_label": "ENCODING_DISC",
            "status": "encoding",
        })

        response = client.post("/api/jobs/2/approve")

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "not in review status" in data["error"].lower()

    def test_approve_job_already_moving(self, client: TestClient) -> None:
        """Test approving a job already in moving status returns 400."""
        client.app.state.jobs.append({
            "id": 3,
            "drive_id": "drive0",
            "disc_label": "MOVING_DISC",
            "status": "moving",
        })

        response = client.post("/api/jobs/3/approve")

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False

    def test_approve_job_preserves_identification(self, client: TestClient) -> None:
        """Test that approving preserves the original identification details."""
        client.app.state.jobs.append({
            "id": 4,
            "drive_id": "drive1",
            "disc_label": "STAR_WARS",
            "content_type": "movie",
            "status": "review",
            "identified_title": "Star Wars: A New Hope",
            "identified_year": 1977,
            "tmdb_id": 11,
            "confidence": 0.82,
        })

        response = client.post("/api/jobs/4/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["identified_title"] == "Star Wars: A New Hope"
        assert data["identified_year"] == 1977

        # Verify all job data is preserved
        job = next(j for j in client.app.state.jobs if j["id"] == 4)
        assert job["tmdb_id"] == 11
        assert job["confidence"] == 0.82
        assert job["content_type"] == "movie"


class TestReviewPage:
    """Tests for the review page."""

    def test_review_page_renders(self, client: TestClient) -> None:
        """Test that the review page renders successfully."""
        response = client.get("/review")

        assert response.status_code == 200
        assert "Review Queue" in response.text

    def test_review_page_shows_jobs(self, client_with_review_job: TestClient) -> None:
        """Test that the review page shows jobs in review status."""
        response = client_with_review_job.get("/review")

        assert response.status_code == 200
        assert "TEST_MOVIE_DISC" in response.text
        assert "Test Movie" in response.text
        assert "2024" in response.text

    def test_review_page_has_approve_button(
        self, client_with_review_job: TestClient
    ) -> None:
        """Test that the review page has approve button for each job."""
        response = client_with_review_job.get("/review")

        assert response.status_code == 200
        assert "Approve" in response.text
        assert "approveJob" in response.text
