"""Tests for the DELETE /api/wanted/{id} endpoint."""

import pytest
from fastapi.testclient import TestClient

from dvdtoplex.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_wanted_items(client: TestClient) -> TestClient:
    """Create a test client with items in the wanted list."""
    app = client.app
    app.state.wanted = [
        {
            "id": 1,
            "title": "The Matrix",
            "year": 1999,
            "notes": "Looking for the original DVD",
        },
        {
            "id": 2,
            "title": "Inception",
            "year": 2010,
            "notes": None,
        },
        {
            "id": 3,
            "title": "Interstellar",
            "year": 2014,
            "notes": "Need the special edition",
        },
    ]
    return client


class TestDeleteWantedEndpoint:
    """Tests for DELETE /api/wanted/{wanted_id} endpoint."""

    def test_delete_wanted_item_success(self, client_with_wanted_items: TestClient) -> None:
        """Test successfully deleting a wanted item."""
        response = client_with_wanted_items.delete("/api/wanted/1")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["wanted_id"] == 1

    def test_delete_wanted_item_removes_from_list(
        self, client_with_wanted_items: TestClient
    ) -> None:
        """Test that the item is actually removed from the wanted list."""
        # Verify initial count
        assert len(client_with_wanted_items.app.state.wanted) == 3

        # Delete the item
        response = client_with_wanted_items.delete("/api/wanted/2")
        assert response.status_code == 200

        # Verify the item was removed
        wanted = client_with_wanted_items.app.state.wanted
        assert len(wanted) == 2
        # Verify the correct item was removed
        ids = [item["id"] for item in wanted]
        assert 2 not in ids
        assert 1 in ids
        assert 3 in ids

    def test_delete_wanted_item_not_found(self, client: TestClient) -> None:
        """Test deleting a non-existent wanted item returns 404."""
        response = client.delete("/api/wanted/999")
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Wanted item not found"

    def test_delete_wanted_item_from_empty_list(self, client: TestClient) -> None:
        """Test deleting from an empty wanted list returns 404."""
        # Ensure the wanted list is empty
        client.app.state.wanted = []
        response = client.delete("/api/wanted/1")
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Wanted item not found"

    def test_delete_multiple_wanted_items(
        self, client_with_wanted_items: TestClient
    ) -> None:
        """Test deleting multiple wanted items sequentially."""
        # Delete first item
        response = client_with_wanted_items.delete("/api/wanted/1")
        assert response.status_code == 200
        assert len(client_with_wanted_items.app.state.wanted) == 2

        # Delete second item
        response = client_with_wanted_items.delete("/api/wanted/3")
        assert response.status_code == 200
        assert len(client_with_wanted_items.app.state.wanted) == 1

        # Verify only item 2 remains
        remaining = client_with_wanted_items.app.state.wanted[0]
        assert remaining["id"] == 2
        assert remaining["title"] == "Inception"

    def test_delete_wanted_item_twice_fails(
        self, client_with_wanted_items: TestClient
    ) -> None:
        """Test that deleting the same item twice fails on second attempt."""
        # First delete succeeds
        response = client_with_wanted_items.delete("/api/wanted/1")
        assert response.status_code == 200

        # Second delete fails with 404
        response = client_with_wanted_items.delete("/api/wanted/1")
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Wanted item not found"
