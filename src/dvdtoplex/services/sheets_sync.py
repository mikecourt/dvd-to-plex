"""Google Sheets sync service."""

import asyncio
import logging
from typing import TYPE_CHECKING

from dvdtoplex.google_sheets import GoogleSheetsClient
from dvdtoplex.plex_scanner import scan_plex_movies
from dvdtoplex.services.base import BaseService

if TYPE_CHECKING:
    from dvdtoplex.config import Config
    from dvdtoplex.database import Database

logger = logging.getLogger(__name__)


class SheetsSyncService(BaseService):
    """Service that syncs movie data to Google Sheets on a schedule."""

    def __init__(self, config: "Config", database: "Database") -> None:
        """Initialize the sync service.

        Args:
            config: Application configuration.
            database: Database instance.
        """
        super().__init__("sheets_sync")
        self._config = config
        self._database = database
        self._sync_interval_hours = config.sheets_sync_interval

    @property
    def is_enabled(self) -> bool:
        """Check if the service is enabled (credentials configured)."""
        return (
            self._config.google_sheets_credentials_file is not None
            and self._config.google_sheets_spreadsheet_id is not None
        )

    async def _run(self) -> None:
        """Main service loop - sync periodically."""
        if not self.is_enabled:
            self._logger.info("Google Sheets sync disabled (no credentials configured)")
            return

        # Initial sync on startup
        await self.sync_now()

        # Then sync on schedule
        while not self.should_stop():
            # Wait for next sync interval
            stopped = await self.wait_for_stop(
                timeout=self._sync_interval_hours * 3600
            )
            if stopped:
                break

            await self.sync_now()

    async def sync_now(self) -> None:
        """Perform a sync immediately."""
        if not self.is_enabled:
            self._logger.warning("Cannot sync - Google Sheets not configured")
            return

        self._logger.info("Starting Google Sheets sync...")

        try:
            # Create client
            client = GoogleSheetsClient(
                self._config.google_sheets_credentials_file,
                self._config.google_sheets_spreadsheet_id,
            )
            client.connect()

            # Scan Plex movies
            movies = scan_plex_movies(self._config.plex_movies_dir)
            self._logger.info("Found %d movies in Plex directory", len(movies))

            # Get wanted items from database
            wanted_items = await self._database.get_wanted()
            wishlist = [
                {
                    "title": item.title,
                    "year": item.year,
                    "poster_path": getattr(item, "poster_path", None),
                }
                for item in wanted_items
            ]
            self._logger.info("Found %d items in wishlist", len(wishlist))

            # Update sheets
            client.update_owned_movies(movies)
            client.update_wishlist(wishlist)

            self._logger.info("Google Sheets sync completed successfully")

        except Exception as e:
            self._logger.error("Google Sheets sync failed: %s", e)
