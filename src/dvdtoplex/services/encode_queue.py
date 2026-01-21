"""Encode queue service for processing ripped content."""

import asyncio
import logging
from pathlib import Path

from dvdtoplex.config import Config
from dvdtoplex.database import Database, JobStatus
from dvdtoplex.handbrake import encode_file

logger = logging.getLogger(__name__)


class EncodeQueue:
    """Processes ripped jobs through encoding."""

    def __init__(self, config: Config, database: Database) -> None:
        """Initialize encode queue.

        Args:
            config: Application configuration.
            database: Database instance.
        """
        self.config = config
        self.database = database
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._current_job: int | None = None

    @property
    def is_running(self) -> bool:
        """Return True if the service is running."""
        return self._running

    @property
    def name(self) -> str:
        """Return the service name."""
        return "EncodeQueue"

    async def start(self) -> None:
        """Start processing encode queue."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Started encode queue processor")

    async def stop(self) -> None:
        """Stop processing encode queue."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Stopped encode queue processor")

    async def _process_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                # Skip if already encoding
                if self._current_job is not None:
                    await asyncio.sleep(self.config.drive_poll_interval)
                    continue

                # Get next ripped job
                jobs = await self.database.get_jobs_by_status(JobStatus.RIPPED)
                if jobs:
                    job = jobs[0]
                    self._current_job = job.id
                    await self._process_job(job.id)
                    self._current_job = None

                await asyncio.sleep(self.config.drive_poll_interval)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in encode queue loop: {e}")
                self._current_job = None
                await asyncio.sleep(self.config.drive_poll_interval)

    async def _process_job(self, job_id: int) -> None:
        """Process a single encode job.

        Args:
            job_id: ID of the job to process.
        """
        try:
            job = await self.database.get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return

            rip_path = job.rip_path
            if not rip_path:
                raise RuntimeError("No rip path found for job")

            input_path = Path(rip_path)
            if not input_path.exists():
                raise RuntimeError(f"Input file not found: {rip_path}")

            disc_label = job.disc_label
            logger.info(f"Starting encode of {disc_label}")

            # Update status to encoding
            await self.database.update_job_status(job_id, JobStatus.ENCODING)

            # Create output path
            output_dir = self.config.encoding_dir / f"job_{job_id}"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{input_path.stem}.mkv"

            # Encode the file
            from dvdtoplex.handbrake import EncodeProgress

            def progress_callback(progress: EncodeProgress) -> None:
                logger.debug(f"Encode progress for job {job_id}: {progress.percent:.1%}")

            await encode_file(
                input_path,
                output_path,
                progress_callback,
            )

            # Update job with encode path
            await self.database.update_job_status(
                job_id,
                JobStatus.ENCODED,
                encode_path=str(output_path),
            )

            logger.info(f"Completed encode of {disc_label} to {output_path}")

        except Exception as e:
            logger.error(f"Error encoding job {job_id}: {e}")
            await self.database.update_job_status(
                job_id,
                JobStatus.FAILED,
                error_message=str(e),
            )

    async def _process_next_job(self) -> None:
        """Process the next ripped job (for test compatibility)."""
        jobs = await self.database.get_jobs_by_status(JobStatus.RIPPED)
        if jobs:
            job = jobs[0]
            await self._process_job(job.id)
