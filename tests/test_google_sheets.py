"""Tests for Google Sheets client."""

import pytest
from unittest.mock import Mock, patch, MagicMock


def test_sheets_client_init_with_credentials(tmp_path):
    """Test client initializes with credentials file."""
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"type": "service_account"}')

    with patch("dvdtoplex.google_sheets.gspread") as mock_gspread:
        mock_gspread.service_account.return_value = Mock()

        from dvdtoplex.google_sheets import GoogleSheetsClient

        client = GoogleSheetsClient(creds_file, "spreadsheet_id")
        client.connect()

        mock_gspread.service_account.assert_called_once_with(filename=str(creds_file))


def test_sheets_client_update_owned_movies():
    """Test updating owned movies sheet."""
    with patch("dvdtoplex.google_sheets.gspread") as mock_gspread:
        mock_gc = Mock()
        mock_spreadsheet = Mock()
        mock_worksheet = Mock()

        mock_gspread.service_account.return_value = mock_gc
        mock_gc.open_by_key.return_value = mock_spreadsheet
        mock_spreadsheet.worksheet.return_value = mock_worksheet

        from dvdtoplex.google_sheets import GoogleSheetsClient

        client = GoogleSheetsClient(None, "spreadsheet_id")
        client._gc = mock_gc

        movies = [
            {"title": "The Matrix", "year": 1999},
            {"title": "Inception", "year": 2010},
        ]

        client.update_owned_movies(movies)

        mock_spreadsheet.worksheet.assert_called_with("Owned")
        # Verify clear and update were called
        assert mock_worksheet.clear.called
        assert mock_worksheet.update.called


def test_sheets_client_update_wishlist_with_posters():
    """Test updating wishlist with poster images."""
    with patch("dvdtoplex.google_sheets.gspread") as mock_gspread:
        mock_gc = Mock()
        mock_spreadsheet = Mock()
        mock_worksheet = Mock()

        mock_gspread.service_account.return_value = mock_gc
        mock_gc.open_by_key.return_value = mock_spreadsheet
        mock_spreadsheet.worksheet.return_value = mock_worksheet

        from dvdtoplex.google_sheets import GoogleSheetsClient

        client = GoogleSheetsClient(None, "spreadsheet_id")
        client._gc = mock_gc

        items = [
            {"title": "Dune", "year": 2021, "poster_path": "/abc123.jpg"},
        ]

        client.update_wishlist(items)

        mock_spreadsheet.worksheet.assert_called_with("Wishlist")
        # Verify the IMAGE formula is included
        call_args = mock_worksheet.update.call_args
        data = call_args[0][0]  # First positional argument
        # Row 1 is header, Row 2 is data
        assert any("=IMAGE(" in str(row) for row in data)


def test_format_poster_url():
    """Test poster URL formatting."""
    from dvdtoplex.google_sheets import format_poster_url

    url = format_poster_url("/abc123.jpg")
    assert url == "https://image.tmdb.org/t/p/w200/abc123.jpg"


def test_format_poster_url_none():
    """Test poster URL formatting with None."""
    from dvdtoplex.google_sheets import format_poster_url

    url = format_poster_url(None)
    assert url == ""


def test_format_image_formula():
    """Test IMAGE formula formatting."""
    from dvdtoplex.google_sheets import format_image_formula

    formula = format_image_formula("https://example.com/image.jpg")
    assert formula == '=IMAGE("https://example.com/image.jpg")'


def test_format_image_formula_empty():
    """Test IMAGE formula with empty URL."""
    from dvdtoplex.google_sheets import format_image_formula

    formula = format_image_formula("")
    assert formula == ""
