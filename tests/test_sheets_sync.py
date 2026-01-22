"""Tests for Google Sheets sync service."""

import sys
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path


# Mock gspread before importing anything that depends on it
@pytest.fixture(autouse=True)
def mock_gspread():
    """Mock gspread module to avoid import errors."""
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"gspread": mock_module}):
        yield mock_module


@pytest.fixture
def mock_config(tmp_path):
    """Create mock config with Google Sheets settings."""
    config = Mock()
    config.google_sheets_credentials_file = tmp_path / "creds.json"
    config.google_sheets_spreadsheet_id = "test_spreadsheet_id"
    config.sheets_sync_interval = 24
    config.plex_movies_dir = tmp_path / "Movies"
    config.plex_movies_dir.mkdir()
    return config


@pytest.fixture
def mock_database():
    """Create mock database."""
    db = AsyncMock()
    db.get_wanted = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_sheets_sync_service_disabled_without_config():
    """Test service is disabled when credentials not configured."""
    config = Mock()
    config.google_sheets_credentials_file = None
    config.google_sheets_spreadsheet_id = None

    from dvdtoplex.services.sheets_sync import SheetsSyncService

    service = SheetsSyncService(config, Mock())

    assert not service.is_enabled


@pytest.mark.asyncio
async def test_sheets_sync_service_enabled_with_config(mock_config, mock_database):
    """Test service is enabled when credentials configured."""
    from dvdtoplex.services.sheets_sync import SheetsSyncService

    service = SheetsSyncService(mock_config, mock_database)

    assert service.is_enabled


@pytest.mark.asyncio
async def test_sheets_sync_performs_sync(mock_config, mock_database, tmp_path):
    """Test sync collects data and updates sheets."""
    # Create test movie folder
    (mock_config.plex_movies_dir / "The Matrix (1999)").mkdir()

    # Mock wanted items
    mock_database.get_wanted.return_value = [
        Mock(title="Dune", year=2021, poster_path="/abc.jpg"),
    ]

    with patch("dvdtoplex.services.sheets_sync.GoogleSheetsClient") as MockClient:
        mock_client = Mock()
        MockClient.return_value = mock_client

        from dvdtoplex.services.sheets_sync import SheetsSyncService

        service = SheetsSyncService(mock_config, mock_database)
        await service.sync_now()

        # Verify client was created and used
        mock_client.connect.assert_called_once()
        mock_client.update_owned_movies.assert_called_once()
        mock_client.update_wishlist.assert_called_once()

        # Verify owned movies data
        owned_call = mock_client.update_owned_movies.call_args[0][0]
        assert len(owned_call) == 1
        assert owned_call[0]["title"] == "The Matrix"

        # Verify wishlist data
        wishlist_call = mock_client.update_wishlist.call_args[0][0]
        assert len(wishlist_call) == 1
        assert wishlist_call[0]["title"] == "Dune"


@pytest.mark.asyncio
async def test_sheets_sync_handles_missing_poster_path(mock_config, mock_database):
    """Test sync handles wanted items without poster_path."""
    mock_database.get_wanted.return_value = [
        Mock(title="Old Movie", year=1990, poster_path=None),
    ]

    with patch("dvdtoplex.services.sheets_sync.GoogleSheetsClient") as MockClient:
        mock_client = Mock()
        MockClient.return_value = mock_client

        from dvdtoplex.services.sheets_sync import SheetsSyncService

        service = SheetsSyncService(mock_config, mock_database)
        await service.sync_now()

        wishlist_call = mock_client.update_wishlist.call_args[0][0]
        assert wishlist_call[0]["poster_path"] is None
