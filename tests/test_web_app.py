"""Tests for the web application."""

import pytest
from fastapi.testclient import TestClient

from dvdtoplex.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the app."""
    app = create_app(database=None)
    return TestClient(app)


def test_create_app_returns_fastapi_instance() -> None:
    """Test that create_app returns a FastAPI application."""
    app = create_app()
    assert app.title == "DVD to Plex"
    assert app.version == "0.1.0"


def test_dashboard_route(client: TestClient) -> None:
    """Test the dashboard route returns HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "DVD to Plex" in response.text
    assert "Dashboard" in response.text


def test_review_route(client: TestClient) -> None:
    """Test the review queue route returns HTML."""
    response = client.get("/review")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Review Queue" in response.text


def test_collection_route(client: TestClient) -> None:
    """Test the collection route returns HTML."""
    response = client.get("/collection")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Collection" in response.text


def test_wanted_route(client: TestClient) -> None:
    """Test the wanted list route returns HTML."""
    response = client.get("/wanted")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Wanted" in response.text


def test_toggle_active_mode_without_database(client: TestClient) -> None:
    """Test toggling active mode without a database returns state."""
    response = client.post("/api/active-mode", json={"active_mode": False})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["active_mode"] is False


def test_navigation_links_present(client: TestClient) -> None:
    """Test that navigation links are present on all pages."""
    routes = ["/", "/review", "/collection", "/wanted"]
    for route in routes:
        response = client.get(route)
        assert 'href="/"' in response.text
        assert 'href="/review"' in response.text
        assert 'href="/collection"' in response.text
        assert 'href="/wanted"' in response.text


def test_dark_theme_styles_present(client: TestClient) -> None:
    """Test that dark theme CSS variables are present."""
    response = client.get("/")
    assert "--bg-primary" in response.text
    assert "--text-primary" in response.text
    assert "--accent" in response.text


def test_static_files_mounted(client: TestClient) -> None:
    """Test that static files directory is mounted and serves files."""
    response = client.get("/static/test.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert ".test-class" in response.text


def test_static_files_404_for_missing_file(client: TestClient) -> None:
    """Test that missing static files return 404."""
    response = client.get("/static/nonexistent.css")
    assert response.status_code == 404
