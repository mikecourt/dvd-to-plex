"""Tests for POST /api/wanted endpoint."""

import pytest
from fastapi.testclient import TestClient

from dvdtoplex.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client with fresh app instance."""
    app = create_app()
    return TestClient(app)


class TestAddToWanted:
    """Tests for POST /api/wanted endpoint."""

    def test_add_movie_to_wanted_success(self, client: TestClient) -> None:
        """Test successfully adding a movie to the wanted list."""
        response = client.post(
            "/api/wanted",
            json={
                "title": "The Matrix",
                "year": 1999,
                "content_type": "movie",
                "tmdb_id": 603,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["id"] == 1
        assert data["title"] == "The Matrix"
        assert data["year"] == 1999
        assert data["content_type"] == "movie"
        assert data["tmdb_id"] == 603

    def test_add_tv_season_to_wanted_success(self, client: TestClient) -> None:
        """Test successfully adding a TV season to the wanted list."""
        response = client.post(
            "/api/wanted",
            json={
                "title": "Breaking Bad",
                "year": 2008,
                "content_type": "tv_season",
                "tmdb_id": 1396,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["title"] == "Breaking Bad"
        assert data["content_type"] == "tv_season"

    def test_add_to_wanted_minimal_fields(self, client: TestClient) -> None:
        """Test adding to wanted list with only required fields."""
        response = client.post(
            "/api/wanted",
            json={
                "title": "Some Movie",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["title"] == "Some Movie"
        assert data["content_type"] == "movie"  # Default value
        assert data["year"] is None
        assert data["tmdb_id"] is None
        assert data["notes"] is None

    def test_add_to_wanted_with_notes(self, client: TestClient) -> None:
        """Test adding to wanted list with notes."""
        response = client.post(
            "/api/wanted",
            json={
                "title": "Inception",
                "year": 2010,
                "content_type": "movie",
                "tmdb_id": 27205,
                "notes": "Looking for the 4K version",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["notes"] == "Looking for the 4K version"

    def test_add_to_wanted_invalid_content_type(self, client: TestClient) -> None:
        """Test that invalid content_type returns an error."""
        response = client.post(
            "/api/wanted",
            json={
                "title": "Some Title",
                "content_type": "invalid_type",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "Invalid content_type" in data["error"]

    def test_add_duplicate_tmdb_id_same_type_fails(self, client: TestClient) -> None:
        """Test that adding a duplicate tmdb_id with same content_type fails."""
        # Add first item
        client.post(
            "/api/wanted",
            json={
                "title": "The Matrix",
                "content_type": "movie",
                "tmdb_id": 603,
            },
        )

        # Try to add same tmdb_id again
        response = client.post(
            "/api/wanted",
            json={
                "title": "The Matrix (Duplicate)",
                "content_type": "movie",
                "tmdb_id": 603,
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["error"]

    def test_add_same_tmdb_id_different_type_succeeds(self, client: TestClient) -> None:
        """Test that same tmdb_id with different content_type succeeds."""
        # Add movie
        client.post(
            "/api/wanted",
            json={
                "title": "Some Title",
                "content_type": "movie",
                "tmdb_id": 12345,
            },
        )

        # Add TV season with same tmdb_id (different content_type)
        response = client.post(
            "/api/wanted",
            json={
                "title": "Some Title",
                "content_type": "tv_season",
                "tmdb_id": 12345,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_add_multiple_items_increments_id(self, client: TestClient) -> None:
        """Test that adding multiple items assigns incrementing IDs."""
        response1 = client.post(
            "/api/wanted",
            json={"title": "Movie 1"},
        )
        response2 = client.post(
            "/api/wanted",
            json={"title": "Movie 2"},
        )
        response3 = client.post(
            "/api/wanted",
            json={"title": "Movie 3"},
        )

        assert response1.json()["id"] == 1
        assert response2.json()["id"] == 2
        assert response3.json()["id"] == 3

    def test_add_to_wanted_missing_title_fails(self, client: TestClient) -> None:
        """Test that missing title field returns validation error."""
        response = client.post(
            "/api/wanted",
            json={
                "year": 2020,
                "content_type": "movie",
            },
        )

        # FastAPI returns 422 for validation errors
        assert response.status_code == 422

    def test_add_to_wanted_item_stored_in_state(self, client: TestClient) -> None:
        """Test that added item is actually stored in app state."""
        client.post(
            "/api/wanted",
            json={
                "title": "Test Movie",
                "year": 2020,
                "content_type": "movie",
                "tmdb_id": 99999,
            },
        )

        # Verify item is in state
        assert len(client.app.state.wanted) == 1
        item = client.app.state.wanted[0]
        assert item["title"] == "Test Movie"
        assert item["year"] == 2020
        assert item["content_type"] == "movie"
        assert item["tmdb_id"] == 99999
        assert "added_at" in item

    def test_add_wanted_stores_poster_path(self, client: TestClient) -> None:
        """Test adding wanted item stores poster_path."""
        response = client.post(
            "/api/wanted",
            json={
                "title": "Dune",
                "year": 2021,
                "content_type": "movie",
                "tmdb_id": 438631,
                "poster_path": "/abc123.jpg",
            },
        )

        assert response.status_code == 200

        # Verify poster_path was stored in app state
        assert len(client.app.state.wanted) == 1
        item = client.app.state.wanted[0]
        assert item.get("poster_path") == "/abc123.jpg"


class TestDeleteFromWanted:
    """Tests for DELETE /api/wanted/{id} endpoint."""

    def test_delete_wanted_item_success(self, client: TestClient) -> None:
        """Test successfully removing an item from the wanted list."""
        # Add an item first
        add_response = client.post(
            "/api/wanted",
            json={
                "title": "Movie to Remove",
                "content_type": "movie",
            },
        )
        item_id = add_response.json()["id"]

        # Delete the item
        response = client.delete(f"/api/wanted/{item_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["wanted_id"] == item_id

        # Verify it's removed from state
        assert len(client.app.state.wanted) == 0

    def test_delete_nonexistent_item_fails(self, client: TestClient) -> None:
        """Test that deleting a nonexistent item returns 404."""
        response = client.delete("/api/wanted/9999")

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"]

    def test_delete_specific_item_leaves_others(self, client: TestClient) -> None:
        """Test that deleting one item leaves other items intact."""
        # Add multiple items
        client.post("/api/wanted", json={"title": "Movie 1"})
        add_response = client.post("/api/wanted", json={"title": "Movie 2"})
        client.post("/api/wanted", json={"title": "Movie 3"})

        item_id = add_response.json()["id"]

        # Delete middle item
        client.delete(f"/api/wanted/{item_id}")

        # Verify other items remain
        assert len(client.app.state.wanted) == 2
        titles = [item["title"] for item in client.app.state.wanted]
        assert "Movie 1" in titles
        assert "Movie 3" in titles
        assert "Movie 2" not in titles
