"""Drive watcher service for automatic disc detection."""

import asyncio
import logging

from dvdtoplex.config import Config
from dvdtoplex.database import Database, ContentType
from dvdtoplex.drives import DriveStatus, get_drive_status

logger = logging.getLogger(__name__)


class DriveWatcher:
    """Monitors DVD drives for disc insertion."""

    def __init__(
        self,
        config: Config,
        database: Database,
        drive_ids: list[str],
    ) -> None:
        """Initialize drive watcher.

        Args:
            config: Application configuration.
            database: Database instance.
            drive_ids: List of drive IDs to monitor.
        """
        self.config = config
        self.database = database
        self.drive_ids = drive_ids
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._previous_states: dict[str, bool] = {}

    @property
    def is_running(self) -> bool:
        """Return True if the service is running."""
        return self._running

    @property
    def name(self) -> str:
        """Return the service name."""
        return "DriveWatcher"

    async def start(self) -> None:
        """Start watching drives."""
        if self._running:
            return

        self._running = True
        # Initialize previous states to False so we detect discs already present
        for drive_id in self.drive_ids:
            self._previous_states[drive_id] = False

        self._task = asyncio.create_task(self._watch_loop())
        logger.info(f"Started watching drives: {self.drive_ids}")

    async def stop(self) -> None:
        """Stop watching drives."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Stopped drive watcher")

    async def _watch_loop(self) -> None:
        """Main watch loop."""
        while self._running:
            try:
                for drive_id in self.drive_ids:
                    status = await get_drive_status(drive_id)
                    previous_has_disc = self._previous_states.get(drive_id, False)

                    if status.has_disc and not previous_has_disc:
                        # Disc was inserted
                        await self._on_disc_inserted(drive_id, status)
                    elif not status.has_disc and previous_has_disc:
                        # Disc was removed
                        logger.info(f"Disc removed from drive {drive_id}")

                    self._previous_states[drive_id] = status.has_disc

                await asyncio.sleep(self.config.drive_poll_interval)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in drive watcher loop: {e}")
                await asyncio.sleep(self.config.drive_poll_interval)

    async def _on_disc_inserted(self, drive_id: str, status: DriveStatus) -> None:
        """Handle disc insertion event.

        Args:
            drive_id: ID of the drive.
            status: Current drive status.
        """
        disc_label = status.disc_label or "UNKNOWN_DISC"
        logger.info(f"Disc inserted in drive {drive_id}: {disc_label}")

        # Check if there's already an active job for this drive
        existing_job = await self.database.get_pending_job_for_drive(drive_id)
        if existing_job:
            logger.info(
                f"Skipping job creation - drive {drive_id} already has active job {existing_job.id}"
            )
            return

        # Create a new job for this disc
        job = await self.database.create_job(
            drive_id=drive_id,
            disc_label=disc_label,
            content_type=ContentType.UNKNOWN,
        )
        logger.info(f"Created job {job.id} for disc {disc_label}")
