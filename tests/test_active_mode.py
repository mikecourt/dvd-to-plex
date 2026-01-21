"""Tests for active mode toggle functionality."""

import pytest
from fastapi.testclient import TestClient

from dvdtoplex.config import Config
from dvdtoplex.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client with default config."""
    config = Config()
    app = create_app(config=config)
    return TestClient(app)


@pytest.fixture
def client_active() -> TestClient:
    """Create a test client with active mode enabled."""
    config = Config(active_mode=True)
    app = create_app(config=config)
    return TestClient(app)


class TestActiveModeToggle:
    """Tests for the POST /api/active-mode endpoint."""

    def test_toggle_from_off_to_on(self, client: TestClient) -> None:
        """Test toggling active mode from OFF to ON."""
        # Initial state should be OFF
        response = client.get("/")
        assert response.status_code == 200
        assert 'data-active="false"' in response.text
        # Check button shows OFF (with possible whitespace)
        assert "OFF" in response.text

        # Toggle to ON
        response = client.post("/api/active-mode")
        assert response.status_code == 200
        data = response.json()
        assert data["active_mode"] is True

        # Verify dashboard shows ON
        response = client.get("/")
        assert response.status_code == 200
        assert 'data-active="true"' in response.text
        # Check button shows ON (with possible whitespace)
        assert "ON" in response.text

    def test_toggle_from_on_to_off(self, client_active: TestClient) -> None:
        """Test toggling active mode from ON to OFF."""
        # Initial state should be ON
        response = client_active.get("/")
        assert response.status_code == 200
        assert 'data-active="true"' in response.text
        # Check button shows ON (with possible whitespace)
        assert "ON" in response.text

        # Toggle to OFF
        response = client_active.post("/api/active-mode")
        assert response.status_code == 200
        data = response.json()
        assert data["active_mode"] is False

        # Verify dashboard shows OFF
        response = client_active.get("/")
        assert response.status_code == 200
        assert 'data-active="false"' in response.text
        # Check button shows OFF (with possible whitespace)
        assert "OFF" in response.text

    def test_double_toggle_returns_to_original(self, client: TestClient) -> None:
        """Test that double toggle returns to original state."""
        # Toggle twice
        response1 = client.post("/api/active-mode")
        assert response1.json()["active_mode"] is True

        response2 = client.post("/api/active-mode")
        assert response2.json()["active_mode"] is False

    def test_dashboard_renders_toggle_button(self, client: TestClient) -> None:
        """Test that the dashboard contains the toggle button."""
        response = client.get("/")
        assert response.status_code == 200
        assert 'id="active-mode-toggle"' in response.text
        assert "btn-toggle" in response.text

    def test_dashboard_includes_javascript(self, client: TestClient) -> None:
        """Test that the dashboard includes the JavaScript for toggle functionality."""
        response = client.get("/")
        assert response.status_code == 200
        assert "fetch('/api/active-mode'" in response.text
        assert "method: 'POST'" in response.text
        assert "window.location.reload()" in response.text


class TestDashboardRoutes:
    """Tests for dashboard page rendering."""

    def test_dashboard_loads(self, client: TestClient) -> None:
        """Test that the dashboard page loads successfully."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Dashboard" in response.text
        assert "DVD to Plex" in response.text

    def test_dashboard_shows_drive_status_section(self, client: TestClient) -> None:
        """Test that the dashboard shows the drive status section."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Drive Status" in response.text

    def test_dashboard_shows_recent_jobs_section(self, client: TestClient) -> None:
        """Test that the dashboard shows the recent jobs section."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Recent Jobs" in response.text
