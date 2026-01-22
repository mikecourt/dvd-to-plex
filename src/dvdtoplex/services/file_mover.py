"""File mover service for moving encoded files to Plex library."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dvdtoplex.config import Config
    from dvdtoplex.database import Database, Job, RipMode

logger = logging.getLogger(__name__)


# Characters that are invalid in filenames across macOS/Windows/Linux
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from a filename.

    Removes characters that are invalid in filenames on common operating systems
    (macOS, Windows, Linux). Also strips leading/trailing whitespace and dots.

    Args:
        filename: The filename to sanitize.

    Returns:
        A sanitized filename safe for use on common filesystems.

    Examples:
        >>> sanitize_filename('Movie: The "Sequel"')
        'Movie The Sequel'
        >>> sanitize_filename("What/If?")
        'WhatIf'
    """
    if not filename:
        return ""

    # Remove invalid characters
    sanitized = INVALID_FILENAME_CHARS.sub("", filename)
    # Replace multiple spaces with single space
    sanitized = re.sub(r"\s+", " ", sanitized)
    # Strip leading/trailing whitespace and dots
    sanitized = sanitized.strip(" .")

    return sanitized


def format_movie_filename(title: str, year: int | None) -> str:
    """Format a movie filename following Plex naming conventions.

    Args:
        title: The movie title.
        year: The movie release year, or None if unknown.

    Returns:
        Formatted filename like "Title (Year).mkv" or "Title.mkv" if year is None.
    """
    sanitized_title = sanitize_filename(title)
    if year:
        return f"{sanitized_title} ({year}).mkv"
    return f"{sanitized_title}.mkv"


def format_movie_folder(title: str, year: int | None) -> str:
    """Format a movie folder name following Plex naming conventions.

    Args:
        title: The movie title.
        year: The movie release year, or None if unknown.

    Returns:
        Formatted folder name like "Title (Year)" or "Title" if year is None.
    """
    sanitized_title = sanitize_filename(title)
    if year:
        return f"{sanitized_title} ({year})"
    return sanitized_title


# Default retry settings for missing Plex directory
DEFAULT_MAX_RETRIES = 10
DEFAULT_RETRY_DELAY = 300  # 5 minutes


@dataclass
class MoveResult:
    """Result of a file move operation."""

    success: bool
    final_path: Path | None = None
    error: str | None = None
    retryable: bool = False  # True if the error is potentially recoverable (e.g., missing directory)


class FileMover:
    """Service for moving encoded files to Plex library directories.

    This service monitors for jobs in MOVING status and moves their encoded
    files to the appropriate Plex library directory with proper naming.
    Movies are placed in a subdirectory named "Title (Year)/".

    Attributes:
        config: Configuration object with Plex directory paths.
        db: Database object for job operations.
    """

    def __init__(
        self,
        config: "Config",
        db: "Database",
        poll_interval: int = 5,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: int = DEFAULT_RETRY_DELAY,
    ) -> None:
        """Initialize the FileMover service.

        Args:
            config: Configuration object with Plex directory paths.
            db: Database object for job operations.
            poll_interval: Seconds between polling for jobs.
            max_retries: Maximum retry attempts for missing Plex directory.
            retry_delay: Seconds to wait before retrying after missing directory.
        """
        self.config = config
        self.db = db
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._retry_counts: dict[int, int] = {}  # Track retries per job

    @property
    def is_running(self) -> bool:
        """Return True if the service is running."""
        return self._running

    @property
    def name(self) -> str:
        """Return the service name."""
        return "FileMover"

    async def start(self) -> None:
        """Start the file mover background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("FileMover started")

    async def stop(self) -> None:
        """Stop the file mover service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("FileMover stopped")

    async def _run(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                await self._process_jobs()
            except Exception as e:
                logger.exception(f"Error in FileMover processing: {e}")
            await asyncio.sleep(self.poll_interval)

    async def _process_jobs(self) -> None:
        """Process all jobs in MOVING status."""
        from dvdtoplex.database import JobStatus

        jobs = await self.db.get_jobs_by_status(JobStatus.MOVING)

        for job in jobs:
            try:
                await self._process_job(job)
            except Exception as e:
                logger.exception(f"Error processing job {job.id}: {e}")
                await self.db.update_job_status(
                    job.id,
                    JobStatus.FAILED,
                    error_message=str(e),
                )

    async def _process_job(self, job: "Job") -> None:
        """Process a single job, moving its encoded file to Plex library.

        Args:
            job: Job object from the database.
        """
        from dvdtoplex.database import JobStatus

        job_id = job.id
        encode_path = Path(job.encode_path) if job.encode_path else None
        content_type = job.content_type.value if job.content_type else "unknown"
        title = job.identified_title
        year = job.identified_year
        tmdb_id = job.tmdb_id
        rip_path = Path(job.rip_path) if job.rip_path else None
        rip_mode = job.rip_mode if hasattr(job, 'rip_mode') else None

        # Validate encode path exists
        if not encode_path or not encode_path.exists():
            error_msg = f"Encoded file not found: {encode_path}"
            logger.error(error_msg)
            await self.db.update_job_status(
                job_id,
                JobStatus.FAILED,
                error_message=error_msg,
            )
            return

        # Validate title is set
        if not title:
            error_msg = "Job missing identified_title"
            logger.error(error_msg)
            await self.db.update_job_status(
                job_id,
                JobStatus.FAILED,
                error_message=error_msg,
            )
            return

        # Move file based on content type
        if content_type == "movie":
            result = await self.move_movie(encode_path, title, year, rip_mode=rip_mode)
        elif content_type == "tv_season":
            # For TV, we'd need season/episode info from the job
            # TODO: Add season/episode fields to Job model
            result = await self._move_tv_episode(
                encode_path, title, 1, 1, None
            )
        else:
            # Treat unknown content type as movie
            logger.warning(f"Unknown content type '{content_type}', treating as movie")
            result = await self.move_movie(encode_path, title, year, rip_mode=rip_mode)

        if not result.success:
            # Handle retryable errors (missing Plex directory)
            if result.retryable:
                retry_count = self._retry_counts.get(job_id, 0)
                if retry_count < self.max_retries:
                    # Schedule retry - job stays in MOVING status
                    new_retry_count = retry_count + 1
                    self._retry_counts[job_id] = new_retry_count
                    logger.warning(
                        f"Job {job_id}: Plex directory not found, "
                        f"retry {new_retry_count}/{self.max_retries} "
                        f"(will retry in {self.retry_delay}s)"
                    )
                    return
                else:
                    # Max retries exceeded
                    logger.error(
                        f"Job {job_id}: Max retries ({self.max_retries}) exceeded "
                        f"for missing Plex directory"
                    )
                    await self.db.update_job_status(
                        job_id,
                        JobStatus.FAILED,
                        error_message=f"Max retries exceeded: {result.error}",
                    )
                    self._retry_counts.pop(job_id, None)
                    return

            # Non-retryable error - fail immediately
            logger.error(f"Failed to move job {job_id}: {result.error}")
            await self.db.update_job_status(
                job_id,
                JobStatus.FAILED,
                error_message=result.error,
            )
            return

        # Update job as complete
        await self.db.update_job_final_path(job_id, str(result.final_path))
        await self.db.update_job_status(job_id, JobStatus.COMPLETE)

        # Add to collection
        await self.db.add_to_collection(
            content_type=content_type,
            title=title,
            year=year,
            tmdb_id=tmdb_id,
            file_path=str(result.final_path),
        )

        # Clean up retry tracking
        self._retry_counts.pop(job_id, None)

        # Clean up source directories
        await self._cleanup(encode_path, rip_path)

        logger.info(f"Job {job_id} completed: {title} -> {result.final_path}")

    def _get_output_directory(self, rip_mode: "RipMode | None") -> Path:
        """Get the output directory based on rip mode.

        Args:
            rip_mode: The rip mode, or None for default (MOVIE).

        Returns:
            Path to the appropriate output directory.
        """
        from dvdtoplex.database import RipMode

        if rip_mode is None:
            return self.config.plex_movies_dir

        if rip_mode == RipMode.TV:
            return self.config.plex_tv_dir
        elif rip_mode == RipMode.HOME_MOVIES:
            return self.config.plex_home_movies_dir
        elif rip_mode == RipMode.OTHER:
            return self.config.plex_other_dir
        else:  # MOVIE is default
            return self.config.plex_movies_dir

    async def move_movie(
        self,
        source: Path,
        title: str,
        year: int | None,
        rip_mode: "RipMode | None" = None,
    ) -> MoveResult:
        """Move a movie file to the Plex movies directory.

        Creates a subdirectory "Title (Year)/" and moves the file inside.
        This follows Plex naming conventions for movies.

        Args:
            source: Path to the encoded file.
            title: Movie title.
            year: Release year or None.

        Returns:
            MoveResult indicating success or failure with final path.

        Example:
            Given title="Inception", year=2010, the file will be moved to:
            {plex_movies_dir}/Inception (2010)/Inception (2010).mkv
        """
        plex_dir = self._get_output_directory(rip_mode)

        # Check Plex directory exists - this is retryable as the drive may be unmounted
        if not plex_dir.exists():
            return MoveResult(
                success=False,
                error=f"Plex movies directory not found: {plex_dir}",
                retryable=True,
            )

        # Create movie subdirectory with "Title (Year)" format
        folder_name = format_movie_folder(title, year)
        movie_dir = plex_dir / folder_name

        try:
            movie_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return MoveResult(success=False, error=f"Failed to create directory: {e}")

        # Create filename with "Title (Year).mkv" format
        filename = format_movie_filename(title, year)
        dest_path = movie_dir / filename

        # Move the file
        try:
            await asyncio.to_thread(shutil.move, str(source), str(dest_path))
            logger.info(f"Moved movie to: {dest_path}")
            return MoveResult(success=True, final_path=dest_path)
        except OSError as e:
            return MoveResult(success=False, error=f"Failed to move file: {e}")

    async def _move_tv_episode(
        self,
        source: Path,
        show: str,
        season: int,
        episode: int,
        episode_title: str | None = None,
    ) -> MoveResult:
        """Move a TV episode file to the Plex TV directory.

        Args:
            source: Path to the encoded file.
            show: TV show name.
            season: Season number.
            episode: Episode number.
            episode_title: Optional episode title.

        Returns:
            MoveResult indicating success or failure.
        """
        plex_dir = self.config.plex_tv_dir

        # Check Plex directory exists - this is retryable as the drive may be unmounted
        if not plex_dir.exists():
            return MoveResult(
                success=False,
                error=f"Plex TV directory not found: {plex_dir}",
                retryable=True,
            )

        # Create show/season subdirectory structure
        sanitized_show = sanitize_filename(show)
        show_dir = plex_dir / sanitized_show
        season_dir = show_dir / f"Season {season:02d}"

        try:
            season_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return MoveResult(success=False, error=f"Failed to create directory: {e}")

        # Format TV filename
        episode_code = f"S{season:02d}E{episode:02d}"
        if episode_title:
            sanitized_ep_title = sanitize_filename(episode_title)
            filename = f"{sanitized_show} - {episode_code} - {sanitized_ep_title}.mkv"
        else:
            filename = f"{sanitized_show} - {episode_code}.mkv"

        dest_path = season_dir / filename

        # Move the file
        try:
            await asyncio.to_thread(shutil.move, str(source), str(dest_path))
            return MoveResult(success=True, final_path=dest_path)
        except OSError as e:
            return MoveResult(success=False, error=f"Failed to move file: {e}")

    async def _cleanup(self, encode_path: Path, rip_path: Path | None) -> None:
        """Clean up source directories after successful move.

        Removes the encode file's parent directory if it's inside encoding_dir,
        and the rip directory if provided.

        Args:
            encode_path: Path to the encoded file (already moved).
            rip_path: Path to the rip staging directory, or None.
        """
        # Clean up encode directory (the parent of the encode file)
        encode_dir = encode_path.parent
        if encode_dir.exists() and encode_dir.is_dir():
            try:
                await asyncio.to_thread(shutil.rmtree, str(encode_dir))
                logger.info(f"Cleaned up encode directory: {encode_dir}")
            except OSError as e:
                logger.error(f"Failed to clean up encode directory {encode_dir}: {e}")

        # Clean up rip directory (rip_path is the file, so use parent directory)
        if rip_path:
            rip_dir = rip_path.parent
            if rip_dir.exists() and rip_dir.is_dir():
                try:
                    await asyncio.to_thread(shutil.rmtree, str(rip_dir))
                    logger.info(f"Cleaned up rip directory: {rip_dir}")
                except OSError as e:
                    logger.error(f"Failed to clean up rip directory {rip_dir}: {e}")
