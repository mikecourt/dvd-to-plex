"""Identifier service for content identification using TMDb and AI."""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from dvdtoplex.ai_identifier import identify_with_ai
from dvdtoplex.config import Config, DEFAULT_AUTO_APPROVE_THRESHOLD
from dvdtoplex.database import ContentType, Database, JobStatus
from dvdtoplex.notifications import Notifier
from dvdtoplex.screenshots import extract_screenshots
from dvdtoplex.tmdb import TMDbClient, MovieMatch, clean_disc_label

logger = logging.getLogger(__name__)

# Re-export for convenience
DEFAULT_AUTO_APPROVE_THRESHOLD = DEFAULT_AUTO_APPROVE_THRESHOLD


def calculate_title_similarity(query: str, title: str) -> float:
    """Calculate similarity score between query and title.

    Args:
        query: Search query string.
        title: Title to compare against.

    Returns:
        Similarity score between 0.0 and 1.0.
    """
    # Handle empty strings
    if not query and not title:
        return 1.0
    if not query or not title:
        return 0.0

    # Normalize: lowercase and remove special characters
    def normalize(s: str) -> str:
        s = s.lower()
        s = re.sub(r"[^\w\s]", "", s)
        return s.strip()

    query_norm = normalize(query)
    title_norm = normalize(title)

    # Exact match
    if query_norm == title_norm:
        return 1.0

    # Check containment
    if query_norm in title_norm or title_norm in query_norm:
        shorter = min(len(query_norm), len(title_norm))
        longer = max(len(query_norm), len(title_norm))
        if longer > 0:
            return shorter / longer
        return 0.0

    # Word overlap
    query_words = set(query_norm.split())
    title_words = set(title_norm.split())

    if not query_words or not title_words:
        return 0.0

    overlap = len(query_words & title_words)
    total = len(query_words | title_words)

    return overlap / total if total > 0 else 0.0


def calculate_popularity_score(
    popularity: float, max_popularity: float = 100.0
) -> float:
    """Calculate normalized popularity score.

    Uses linear scaling where max_popularity maps to 1.0.

    Args:
        popularity: TMDb popularity value.
        max_popularity: Value that maps to 1.0 (default 100.0).

    Returns:
        Normalized score between 0.0 and 1.0.
    """
    if popularity <= 0:
        return 0.0
    # Linear scaling capped at 1.0
    return min(1.0, popularity / max_popularity)


@dataclass
class IdentificationResult:
    """Result of content identification."""

    content_type: ContentType
    title: str
    year: int | None
    tmdb_id: int
    confidence: float
    needs_review: bool
    alternatives: list[MovieMatch]
    poster_path: str | None = None


def calculate_confidence(
    query: str,
    result_title: str,
    popularity: float,
    is_first_result: bool,
) -> float:
    """Calculate confidence score for a match.

    Based on title similarity, popularity, and result ranking.

    Args:
        query: Original search query.
        result_title: Title of the match.
        popularity: TMDb popularity score.
        is_first_result: Whether this is the first result (gets bonus).

    Returns:
        Confidence score between 0.0 and 1.0.
    """
    title_score = calculate_title_similarity(query, result_title)
    pop_score = calculate_popularity_score(popularity)

    # Weights: 60% title match, 25% popularity, 15% rank bonus
    rank_bonus = 0.15 if is_first_result else 0.0
    confidence = (title_score * 0.60) + (pop_score * 0.25) + rank_bonus

    return min(1.0, max(0.0, confidence))


class IdentifierService:
    """Service for identifying encoded content."""

    def __init__(
        self,
        db: Database,
        config: Config,
        tmdb_client: TMDbClient | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        """Initialize identifier service.

        Args:
            db: Database instance.
            config: Application configuration.
            tmdb_client: Optional TMDb client (for testing). If None, creates one.
            notifier: Optional notifier (for testing). If None, creates one from config.
        """
        self.db = db
        self.config = config
        self._tmdb_client = tmdb_client
        self._notifier = notifier or Notifier(
            user_key=config.pushover_user_key,
            api_token=config.pushover_api_token,
        )
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        """Return True if the service is running."""
        return self._running

    @property
    def name(self) -> str:
        """Return the service name."""
        return "IdentifierService"

    async def start(self) -> None:
        """Start the identifier service."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Started identifier service")

    async def stop(self) -> None:
        """Stop the identifier service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Stopped identifier service")

    async def _process_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                await self._process_encoded_jobs()
                await asyncio.sleep(self.config.drive_poll_interval)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in identifier loop: {e}")
                await asyncio.sleep(self.config.drive_poll_interval)

    async def _process_encoded_jobs(self) -> None:
        """Process all encoded jobs needing identification."""
        jobs = await self.db.get_jobs_by_status(JobStatus.ENCODED)

        for job in jobs:
            await self._process_single_job(job.id, job.disc_label)

    async def _process_single_job(self, job_id: int, disc_label: str) -> None:
        """Process a single identification job.

        Args:
            job_id: ID of the job to identify.
            disc_label: Disc label to identify.
        """
        try:
            logger.info(f"Identifying content for {disc_label}")

            # Update status
            await self.db.update_job_status(job_id, JobStatus.IDENTIFYING)

            # Get the job record to access encode_path
            job = await self.db.get_job(job_id)

            # Check if job is already pre-identified (has title set by user)
            # Any job with identified_title set is considered pre-identified and skips auto-ID
            if job and job.identified_title:
                logger.info(
                    f"Job {job_id} already identified as '{job.identified_title}', "
                    "skipping automatic identification"
                )
                await self.db.update_job_status(job_id, JobStatus.MOVING)
                return

            encode_path = Path(job.encode_path) if job and job.encode_path else None

            # Extract screenshots for AI identification
            screenshot_paths: list[Path] = []
            if encode_path and encode_path.exists():
                screenshot_dir = self.config.staging_dir / f"job_{job_id}" / "screenshots"
                screenshot_paths = await extract_screenshots(encode_path, screenshot_dir)
                if screenshot_paths:
                    logger.info(f"Extracted {len(screenshot_paths)} screenshots for job {job_id}")

            # Identify the content (passing screenshots for AI fallback)
            result = await self.identify(disc_label, screenshot_paths)

            if result.tmdb_id is not None:
                # Update job with identification
                await self.db.update_job_identification(
                    job_id,
                    result.content_type,
                    result.title,
                    result.year,
                    result.tmdb_id,
                    result.confidence,
                    poster_path=result.poster_path,
                )

                # Transition based on confidence
                if result.needs_review:
                    await self.db.update_job_status(job_id, JobStatus.REVIEW)
                    logger.info(
                        f"Job {job_id} needs review: {result.title} "
                        f"({result.confidence:.0%} confidence)"
                    )
                    # Send push notification
                    web_url = f"http://{self.config.web_host}:{self.config.web_port}/review"
                    await self._notifier.notify_review_needed(
                        disc_label, result.confidence, web_url
                    )
                else:
                    await self.db.update_job_status(job_id, JobStatus.MOVING)
                    logger.info(
                        f"Job {job_id} auto-approved: {result.title} "
                        f"({result.confidence:.0%} confidence)"
                    )
            else:
                # No match found, needs review
                await self.db.update_job_status(job_id, JobStatus.REVIEW)
                logger.info(
                    f"Job {job_id} could not be identified, needs manual review"
                )
                # Send push notification
                web_url = f"http://{self.config.web_host}:{self.config.web_port}/review"
                await self._notifier.notify_review_needed(
                    disc_label, 0.0, web_url
                )

        except Exception as e:
            logger.error(f"Error identifying job {job_id}: {e}")
            await self.db.update_job_status(
                job_id,
                JobStatus.FAILED,
                error_message=str(e),
            )
            # Send error notification
            await self._notifier.notify_error(disc_label, str(e))

    async def identify(
        self,
        disc_label: str,
        screenshot_paths: list[Path] | None = None,
    ) -> IdentificationResult:
        """Identify content from a disc label.

        First tries TMDb search. If that fails or has low confidence,
        falls back to AI identification using screenshots.

        Args:
            disc_label: Raw disc label.
            screenshot_paths: Optional paths to screenshots for AI identification.

        Returns:
            IdentificationResult. If no matches, returns UNKNOWN with tmdb_id=None.
        """
        # Clean the disc label for searching
        cleaned = clean_disc_label(disc_label)
        logger.debug(f"Cleaned disc label: '{disc_label}' -> '{cleaned}'")

        # Use injected client or create new one
        # NOTE: TV identification disabled - movies only for now
        if self._tmdb_client:
            client = self._tmdb_client
            movie_results = await client.search_movie(cleaned)
        else:
            async with TMDbClient(self.config.tmdb_api_token) as client:
                movie_results = await client.search_movie(cleaned)

        # Calculate confidence for each result (first result gets bonus)
        scored_movies: list[tuple[float, MovieMatch]] = []
        for i, movie in enumerate(movie_results):
            conf = calculate_confidence(
                cleaned, movie.title, movie.popularity, is_first_result=(i == 0)
            )
            scored_movies.append((conf, movie))

        # Sort by confidence
        scored_movies.sort(key=lambda x: x[0], reverse=True)

        # Get best match
        best_movie = scored_movies[0] if scored_movies else None

        # If no results at all, try AI identification
        if not best_movie:
            if screenshot_paths and self.config.anthropic_api_key:
                logger.info(f"No TMDb results, trying AI identification for {disc_label}")
                ai_result = await identify_with_ai(
                    disc_label, screenshot_paths, self.config.anthropic_api_key
                )
                if ai_result and ai_result.title:
                    # AI found something - search TMDb with AI's suggestion (movies only)
                    async with TMDbClient(self.config.tmdb_api_token) as client:
                        ai_search = await client.search_movie(
                            ai_result.title, ai_result.year
                        )
                        if ai_search:
                            return IdentificationResult(
                                content_type=ContentType.MOVIE,
                                title=ai_search[0].title,
                                year=ai_search[0].year,
                                tmdb_id=ai_search[0].tmdb_id,
                                confidence=ai_result.confidence,
                                needs_review=ai_result.confidence < self.config.auto_approve_threshold,
                                alternatives=ai_search[1:5],
                                poster_path=ai_search[0].poster_path,
                            )

            # No results found
            return IdentificationResult(
                content_type=ContentType.UNKNOWN,
                title="",
                year=None,
                tmdb_id=None,  # type: ignore[arg-type]
                confidence=0.0,
                needs_review=True,
                alternatives=[],
            )

        # Use best movie match (TV disabled for now)
        confidence, match = best_movie
        content_type = ContentType.MOVIE
        title = match.title
        year = match.year
        tmdb_id = match.tmdb_id
        poster_path = match.poster_path

        # Get alternatives (excluding the best match)
        alternatives: list[MovieMatch] = []
        for _, m in scored_movies[1:5]:
            alternatives.append(m)

        # Determine if review is needed
        needs_review = confidence < self.config.auto_approve_threshold

        return IdentificationResult(
            content_type=content_type,
            title=title,
            year=year,
            tmdb_id=tmdb_id,
            confidence=confidence,
            needs_review=needs_review,
            alternatives=alternatives,
            poster_path=poster_path,
        )

    async def identify_and_update_job(
        self,
        job_id: int,
        title: str,
        year: int | None,
        tmdb_id: int,
    ) -> None:
        """Manually identify a job and update it to MOVING status.

        Args:
            job_id: ID of the job to update.
            title: Identified title.
            year: Identified year.
            tmdb_id: TMDb ID.
        """
        # Fetch poster_path from TMDb
        poster_path: str | None = None
        try:
            if self._tmdb_client:
                # Use injected client (for testing)
                details = await self._tmdb_client.get_movie_details(tmdb_id)
                if details:
                    poster_path = details.poster_path
            else:
                async with TMDbClient(self.config.tmdb_api_token) as client:
                    details = await client.get_movie_details(tmdb_id)
                    if details:
                        poster_path = details.poster_path
        except Exception as e:
            logger.warning(f"Could not fetch poster for tmdb_id {tmdb_id}: {e}")

        await self.db.update_job_identification(
            job_id=job_id,
            content_type=ContentType.MOVIE,
            title=title,
            year=year,
            tmdb_id=tmdb_id,
            confidence=1.0,
            poster_path=poster_path,
        )
        await self.db.update_job_status(job_id, JobStatus.MOVING)
