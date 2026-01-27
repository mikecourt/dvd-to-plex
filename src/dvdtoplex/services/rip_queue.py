"""Rip queue service for processing pending rip jobs."""

import asyncio
import logging

from dvdtoplex.config import Config
from dvdtoplex.database import Database, JobStatus
from dvdtoplex.drives import eject_drive
from dvdtoplex.makemkv import DiscReadError, TitleInfo, get_disc_info, rip_title
from dvdtoplex.notifications import Notifier

logger = logging.getLogger(__name__)

# Minimum duration for main feature (60 minutes in seconds)
MIN_FEATURE_DURATION = 60 * 60
MIN_MAIN_FEATURE_DURATION = MIN_FEATURE_DURATION  # Alias for compatibility


def select_main_title(titles: list[TitleInfo]) -> TitleInfo | None:
    """Select the main title from a list of titles.

    Chooses the longest title that is at least 60 minutes.

    Args:
        titles: List of titles from the disc.

    Returns:
        The selected main title, or None if no suitable title found.
    """
    # Filter to titles at least 60 minutes
    feature_titles = [t for t in titles if t.duration_seconds >= MIN_FEATURE_DURATION]

    if not feature_titles:
        # Fall back to longest title if none meet minimum
        if titles:
            return max(titles, key=lambda t: t.duration_seconds)
        return None

    # Return longest feature title
    return max(feature_titles, key=lambda t: t.duration_seconds)


class RipQueue:
    """Processes pending rip jobs from the queue."""

    def __init__(
        self,
        config: Config,
        database: Database,
        drive_ids: list[str],
        notifier: Notifier | None = None,
    ) -> None:
        """Initialize rip queue.

        Args:
            config: Application configuration.
            database: Database instance.
            drive_ids: List of drive IDs to process.
            notifier: Optional notifier (for testing). If None, creates one from config.
        """
        self.config = config
        self.database = database
        self.drive_ids = drive_ids
        self._notifier = notifier or Notifier(
            user_key=config.pushover_user_key,
            api_token=config.pushover_api_token,
        )
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._active_jobs: dict[str, int] = {}  # drive_id -> job_id
        # Alias for test compatibility
        self._active_rips: dict[str, asyncio.Task[None]] = {}

    @property
    def is_running(self) -> bool:
        """Return True if the service is running."""
        return self._running

    @property
    def name(self) -> str:
        """Return the service name."""
        return "RipQueue"

    async def start(self) -> None:
        """Start processing rip queue."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Started rip queue processor")

    async def stop(self) -> None:
        """Stop processing rip queue."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Stopped rip queue processor")

    async def _process_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                # Check each drive for pending jobs
                for drive_id in self.drive_ids:
                    # Skip if already ripping on this drive
                    if drive_id in self._active_jobs:
                        continue

                    job = await self.database.get_pending_job_for_drive(drive_id)
                    if job:
                        # Only start ripping if job is PENDING (not already RIPPING)
                        # Jobs in RIPPING status may have MakeMKV processes still running from before restart
                        if job.status == JobStatus.RIPPING:
                            logger.debug(f"Job {job.id} already ripping, skipping")
                            continue
                        # Start ripping in background
                        self._active_jobs[drive_id] = job.id
                        asyncio.create_task(self._process_job(drive_id, job.id))

                await asyncio.sleep(self.config.drive_poll_interval)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in rip queue loop: {e}")
                await asyncio.sleep(self.config.drive_poll_interval)

    async def _process_job(self, drive_id: str, job_id: int) -> None:
        """Process a single rip job.

        Args:
            drive_id: ID of the drive to rip from.
            job_id: ID of the job to process.
        """
        try:
            job = await self.database.get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return

            disc_label = job.disc_label
            logger.info(f"Starting rip of {disc_label} from drive {drive_id}")

            # Update status to ripping
            await self.database.update_job_status(job_id, JobStatus.RIPPING)

            # Wait for disc to spin up and be ready before reading
            logger.debug(f"Waiting for disc to be ready in drive {drive_id}")
            await asyncio.sleep(8)

            # Get disc info (raises DiscReadError with details if no titles found)
            titles = await get_disc_info(drive_id)

            # Select main title
            main_title = select_main_title(titles)
            if not main_title:
                raise RuntimeError("No suitable title found")

            logger.info(
                f"Selected title {main_title.index} "
                f"({main_title.duration_seconds // 60} min)"
            )

            # Create output directory
            output_dir = self.config.staging_dir / f"job_{job_id}"

            # Rip the title
            def progress_callback(progress: float) -> None:
                logger.debug(f"Rip progress for job {job_id}: {progress:.1%}")

            ripped_path = await rip_title(
                drive_id,
                main_title.index,
                output_dir,
                progress_callback,
            )
            # rip_title now raises RipError on failure, so ripped_path is always valid here

            # Update job with rip path
            await self.database.update_job_status(
                job_id,
                JobStatus.RIPPED,
                rip_path=str(ripped_path),
            )

            logger.info(f"Completed rip of {disc_label} to {ripped_path}")

            # Eject disc
            await eject_drive(drive_id)

        except DiscReadError as e:
            # Include diagnostic details from MakeMKV in error message
            error_msg = str(e)
            if e.details:
                error_msg = f"{e}: {e.details}"
            logger.error(f"Error ripping job {job_id}: {error_msg}")
            await self.database.update_job_status(
                job_id,
                JobStatus.FAILED,
                error_message=error_msg,
            )
            await self._notifier.notify_error(disc_label, error_msg)
            await eject_drive(drive_id)

        except Exception as e:
            logger.error(f"Error ripping job {job_id}: {e}")
            await self.database.update_job_status(
                job_id,
                JobStatus.FAILED,
                error_message=str(e),
            )
            # Notify of rip failure
            await self._notifier.notify_error(disc_label, str(e))
            # Eject disc on failure too
            await eject_drive(drive_id)

        finally:
            # Remove from active jobs
            self._active_jobs.pop(drive_id, None)

    # Compatibility methods for tests
    async def _rip_job(self, job_id: int, drive_id: str) -> None:
        """Compatibility wrapper for _process_job (params reversed)."""
        await self._process_job(drive_id, job_id)

    async def _process_pending_jobs(self) -> None:
        """Process pending jobs once (for test compatibility)."""
        for drive_id in self.drive_ids:
            # Skip if already ripping on this drive
            if drive_id in self._active_rips:
                continue
            if drive_id in self._active_jobs:
                continue

            job = await self.database.get_pending_job_for_drive(drive_id)
            if job:
                self._active_jobs[drive_id] = job.id
                asyncio.create_task(self._process_job(drive_id, job.id))
