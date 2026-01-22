"""Google Sheets client for syncing movie data."""

import logging
from pathlib import Path
from typing import Any

import gspread

logger = logging.getLogger(__name__)

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w200"


def format_poster_url(poster_path: str | None) -> str:
    """Format a TMDb poster path into a full URL.

    Args:
        poster_path: TMDb poster path (e.g., "/abc123.jpg") or None.

    Returns:
        Full poster URL or empty string if no path.
    """
    if not poster_path:
        return ""
    return f"{TMDB_IMAGE_BASE}{poster_path}"


def format_image_formula(url: str) -> str:
    """Format a URL as a Google Sheets IMAGE formula.

    Args:
        url: Image URL.

    Returns:
        Google Sheets IMAGE formula or empty string if no URL.
    """
    if not url:
        return ""
    return f'=IMAGE("{url}")'


class GoogleSheetsClient:
    """Client for interacting with Google Sheets."""

    def __init__(
        self,
        credentials_file: Path | None,
        spreadsheet_id: str,
    ) -> None:
        """Initialize the Google Sheets client.

        Args:
            credentials_file: Path to service account JSON file.
            spreadsheet_id: Google Sheets spreadsheet ID.
        """
        self._credentials_file = credentials_file
        self._spreadsheet_id = spreadsheet_id
        self._gc: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None

    def connect(self) -> None:
        """Connect to Google Sheets API."""
        if self._credentials_file:
            self._gc = gspread.service_account(filename=str(self._credentials_file))
        else:
            # For testing - client must be set manually
            return
        self._spreadsheet = self._gc.open_by_key(self._spreadsheet_id)
        logger.info("Connected to Google Sheets: %s", self._spreadsheet.title)

    def _get_spreadsheet(self) -> gspread.Spreadsheet:
        """Get the spreadsheet, connecting if needed."""
        if self._spreadsheet is None:
            if self._gc is None:
                raise RuntimeError("Not connected to Google Sheets")
            self._spreadsheet = self._gc.open_by_key(self._spreadsheet_id)
        return self._spreadsheet

    def update_owned_movies(self, movies: list[dict[str, Any]]) -> None:
        """Update the Owned sheet with movie data.

        Args:
            movies: List of dicts with 'title' and 'year' keys.
        """
        spreadsheet = self._get_spreadsheet()
        worksheet = spreadsheet.worksheet("Owned")

        # Clear existing data
        worksheet.clear()

        # Prepare data with header
        data = [["Title", "Year"]]
        for movie in movies:
            data.append([movie["title"], movie["year"] or ""])

        # Write all data
        worksheet.update(data, value_input_option="USER_ENTERED")
        logger.info("Updated Owned sheet with %d movies", len(movies))

    def update_wishlist(self, items: list[dict[str, Any]]) -> None:
        """Update the Wishlist sheet with wanted items.

        Args:
            items: List of dicts with 'title', 'year', and 'poster_path' keys.
        """
        spreadsheet = self._get_spreadsheet()
        worksheet = spreadsheet.worksheet("Wishlist")

        # Clear existing data
        worksheet.clear()

        # Prepare data with header
        data = [["Title", "Year", "Poster URL", "Poster"]]
        for item in items:
            poster_url = format_poster_url(item.get("poster_path"))
            image_formula = format_image_formula(poster_url)
            data.append([
                item["title"],
                item.get("year") or "",
                poster_url,
                image_formula,
            ])

        # Write all data
        worksheet.update(data, value_input_option="USER_ENTERED")
        logger.info("Updated Wishlist sheet with %d items", len(items))
