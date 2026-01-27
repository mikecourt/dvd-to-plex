"""FastAPI web application for DVD to Plex pipeline."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dvdtoplex.config import Config
    from dvdtoplex.database import Database
    from dvdtoplex.services.drive_watcher import DriveWatcher


def format_file_size(size_bytes: int) -> str:
    """Format bytes as human-readable size.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Human-readable size string (e.g., "1.5 GB").
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_job_file_size(job_id: int, status: str, config: "Config") -> str | None:
    """Get current file size for a job being ripped or encoded.

    Args:
        job_id: The job ID.
        status: Current job status.
        config: Application config with directory paths.

    Returns:
        Human-readable file size or None if not applicable.
    """
    if status == "ripping":
        job_dir = config.staging_dir / f"job_{job_id}"
    elif status == "encoding":
        job_dir = config.encoding_dir / f"job_{job_id}"
    else:
        return None

    if not job_dir.exists():
        return None

    # Sum all mkv files in the directory
    total_size = 0
    for mkv_file in job_dir.glob("*.mkv"):
        try:
            total_size += mkv_file.stat().st_size
        except OSError:
            pass

    if total_size == 0:
        return None

    return format_file_size(total_size)


class ActiveModeRequest(BaseModel):
    """Request body for active mode toggle."""

    active_mode: bool


class RipModeRequest(BaseModel):
    """Request body for rip mode selection."""

    mode: str


class IdentifyRequest(BaseModel):
    """Request body for job identification update."""

    title: str
    year: int | None = None
    tmdb_id: int | None = None


class WantedRequest(BaseModel):
    """Request body for adding to wanted list."""

    title: str
    year: int | None = None
    content_type: str = "movie"
    tmdb_id: int | None = None
    poster_path: str | None = None
    notes: str | None = None


def create_app(
    database: Database | None = None,
    drive_watcher: DriveWatcher | None = None,
    config: Config | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        database: Optional database instance for persistent storage.
        drive_watcher: Optional drive watcher instance for drive operations.
        config: Optional configuration instance for app settings.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="DVD to Plex",
        description="Automated DVD ripping pipeline with web UI",
        version="0.1.0",
    )

    # Get paths for static files and templates
    web_dir = Path(__file__).parent
    static_dir = web_dir / "static"
    templates_dir = web_dir / "templates"

    # Mount static files directory
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Configure Jinja2 templates
    templates = Jinja2Templates(directory=templates_dir)

    # Store templates in app state for access in routes
    app.state.templates = templates

    # Store injected dependencies
    app.state.database = database
    app.state.drive_watcher = drive_watcher
    app.state.config = config

    # Initialize active_mode from config if provided, otherwise default to False
    app.state.active_mode = config.active_mode if config is not None else False

    # In-memory state for demo (will be replaced by database in full implementation)
    initial_jobs: list[dict[str, Any]] = []
    initial_collection: list[dict[str, Any]] = []
    initial_wanted: list[dict[str, Any]] = []
    app.state.jobs = initial_jobs
    app.state.collection = initial_collection
    app.state.wanted = initial_wanted

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        """Render the main dashboard page.

        Shows active mode toggle, drive status, and recent jobs.
        """
        # Get current rip mode
        current_mode = "movie"
        if app.state.database is not None:
            current_mode = await app.state.database.get_setting("current_mode") or "movie"

        # Fetch recent jobs from database if available
        if app.state.database is not None:
            db_jobs = await app.state.database.get_recent_jobs(20, exclude_archived=True)
            recent_jobs = [
                {
                    "id": job.id,
                    "disc_label": job.disc_label,
                    "status": job.status.value,
                    "identified_title": job.identified_title,
                    "identified_year": job.identified_year,
                    "content_type": job.content_type.value if job.content_type else None,
                    "rip_mode": job.rip_mode.value if job.rip_mode else "movie",
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                    "file_size": get_job_file_size(job.id, job.status.value, app.state.config) if app.state.config else None,
                }
                for job in db_jobs
            ]
        else:
            recent_jobs = app.state.jobs[-20:]

        # Get real drive status if drive_watcher is available
        from dvdtoplex.drives import get_drive_status

        drives = []
        # Drive config: (drutil_id, display_name)
        drive_config = [
            ("1", "Top Drive"),
            ("2", "Bottom Drive"),
        ]
        for i, (drive_id, drive_name) in enumerate(drive_config):
            status = await get_drive_status(drive_id)
            # Check if this drive has an active ripping job
            ripping_job = next(
                (job for job in recent_jobs
                 if job.get("status") == "ripping" and job.get("drive_id") == drive_id),
                None
            )
            processing = ripping_job is not None
            # Use job's disc label if drive status timed out during rip
            disc_label = status.disc_label or (ripping_job.get("disc_label") if ripping_job else None)
            drives.append({
                "id": i,
                "name": drive_name,
                "has_disc": status.has_disc or processing,  # Show disc present if ripping
                "processing": processing,
                "disc_label": disc_label,
                "status": "ripping" if processing else None,
            })

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "active_mode": app.state.active_mode,
                "current_mode": current_mode,
                "drives": drives,
                "recent_jobs": recent_jobs,
            },
        )

    @app.post("/api/active-mode")
    async def toggle_active_mode(
        body: ActiveModeRequest | None = None,
    ) -> JSONResponse:
        """Toggle the active mode on/off.

        If body is provided with active_mode value, sets to that value.
        If no body is provided, toggles the current state.

        Args:
            body: Optional request body containing active_mode boolean.

        Returns:
            JSON response with success status and new active_mode state.
        """
        if body is not None:
            app.state.active_mode = body.active_mode
        else:
            app.state.active_mode = not app.state.active_mode
        return JSONResponse(
            content={
                "success": True,
                "active_mode": app.state.active_mode,
            }
        )

    @app.get("/api/mode")
    async def get_current_mode() -> JSONResponse:
        """Get the current ripping mode.

        Returns:
            JSON with current mode.
        """
        if app.state.database is None:
            return JSONResponse(content={"mode": "movie"})

        mode = await app.state.database.get_setting("current_mode")
        return JSONResponse(content={"mode": mode or "movie"})

    @app.post("/api/mode")
    async def set_current_mode(body: RipModeRequest) -> JSONResponse:
        """Set the current ripping mode.

        Args:
            body: JSON body with 'mode' key.

        Returns:
            JSON with success status.
        """
        mode = body.mode
        valid_modes = {"movie", "tv", "home_movies", "other"}

        if mode not in valid_modes:
            return JSONResponse(
                content={"detail": f"Invalid mode. Must be one of: {valid_modes}"},
                status_code=400,
            )

        if app.state.database is not None:
            await app.state.database.set_setting("current_mode", mode)

        return JSONResponse(content={"success": True, "mode": mode})

    @app.get("/review", response_class=HTMLResponse)
    async def review(request: Request) -> HTMLResponse:
        """Render the review queue page.

        Shows jobs in REVIEW status that need manual identification.
        """
        # Fetch from database if available
        if app.state.database is not None:
            from dvdtoplex.database import JobStatus

            db_jobs = await app.state.database.get_jobs_by_status(JobStatus.REVIEW)
            review_jobs = []
            for job in db_jobs:
                # Check for screenshots
                screenshots = []
                if app.state.config:
                    screenshot_dir = app.state.config.staging_dir / f"job_{job.id}" / "screenshots"
                    if screenshot_dir.exists():
                        screenshots = [f"/screenshots/{job.id}/{f.name}" for f in sorted(screenshot_dir.glob("*.jpg"))]

                review_jobs.append({
                    "id": job.id,
                    "disc_label": job.disc_label,
                    "status": job.status.value,
                    "identified_title": job.identified_title,
                    "identified_year": job.identified_year,
                    "confidence": job.confidence,
                    "content_type": job.content_type.value if job.content_type else None,
                    "rip_mode": job.rip_mode.value if job.rip_mode else "movie",
                    "screenshots": screenshots,
                    "poster_url": f"https://image.tmdb.org/t/p/w200{job.poster_path}" if job.poster_path else None,
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                })
        else:
            # Fall back to in-memory state
            review_jobs = [j for j in app.state.jobs if j.get("status") == "review"]
        return templates.TemplateResponse(
            "review.html",
            {
                "request": request,
                "jobs": review_jobs,
            },
        )

    @app.get("/screenshots/{job_id}/{filename}")
    async def get_screenshot(job_id: int, filename: str) -> FileResponse:
        """Serve a screenshot image for a job.

        Args:
            job_id: The job ID.
            filename: The screenshot filename.

        Returns:
            The screenshot image file.
        """
        if app.state.config is None:
            return JSONResponse(content={"error": "Config not available"}, status_code=500)

        screenshot_path = app.state.config.staging_dir / f"job_{job_id}" / "screenshots" / filename
        if not screenshot_path.exists():
            return JSONResponse(content={"error": "Screenshot not found"}, status_code=404)

        return FileResponse(screenshot_path, media_type="image/jpeg")

    @app.get("/collection", response_class=HTMLResponse)
    async def collection(request: Request) -> HTMLResponse:
        """Render the collection page.

        Shows owned content that has been ripped to Plex.
        """
        # Fetch from database if available, otherwise use in-memory state
        if app.state.database is not None:
            items = await app.state.database.get_collection()
        else:
            items = app.state.collection
        return templates.TemplateResponse(
            "collection.html",
            {
                "request": request,
                "items": items,
            },
        )

    @app.get("/wanted", response_class=HTMLResponse)
    async def wanted(request: Request) -> HTMLResponse:
        """Render the wanted list page.

        Shows titles the user is searching for.
        """
        # Fetch from database if available
        if app.state.database is not None:
            db_items = await app.state.database.get_wanted()
            items = [
                {
                    "id": item.id,
                    "title": item.title,
                    "year": item.year,
                    "content_type": item.content_type.value,
                    "tmdb_id": item.tmdb_id,
                    "poster_path": item.poster_path,
                    "notes": item.notes,
                    "added_at": item.added_at.isoformat() if item.added_at else None,
                }
                for item in db_items
            ]
        else:
            items = app.state.wanted

        return templates.TemplateResponse(
            "wanted.html",
            {
                "request": request,
                "items": items,
            },
        )

    # API endpoints for review page actions
    @app.post("/api/jobs/{job_id}/approve")
    async def approve_job(job_id: int, request: Request) -> JSONResponse:
        """Approve a job's identification and move to MOVING status.

        Args:
            job_id: The ID of the job to approve.
            request: Optional JSON body with 'mode' to override rip_mode.

        Returns:
            JSON response with success status.
        """
        # Use database if available
        if app.state.database is not None:
            from dvdtoplex.database import JobStatus, RipMode

            job = await app.state.database.get_job(job_id)
            if job is None:
                return JSONResponse(
                    content={"detail": "Job not found"},
                    status_code=404,
                )
            if job.status != JobStatus.REVIEW:
                return JSONResponse(
                    content={
                        "detail": f"Job is not in REVIEW status (current: {job.status.value})"
                    },
                    status_code=400,
                )

            # Check for mode override in request body
            try:
                body = await request.json()
                mode_str = body.get("mode")
                if mode_str:
                    try:
                        new_mode = RipMode(mode_str)
                        await app.state.database.update_job_rip_mode(job_id, new_mode)
                    except ValueError:
                        pass  # Invalid mode, ignore
            except Exception:
                pass  # No body or invalid JSON, proceed without mode change

            await app.state.database.update_job_status(job_id, JobStatus.MOVING)
            return JSONResponse(
                content={
                    "success": True,
                    "job_id": job_id,
                    "status": "moving",
                }
            )

        # Fall back to in-memory state
        for job in app.state.jobs:
            if job.get("id") == job_id:
                # Validate job is in review status
                if job.get("status") != "review":
                    return JSONResponse(
                        content={
                            "success": False,
                            "error": f"Job is not in review status (current: {job.get('status')})",
                        },
                        status_code=400,
                    )
                job["status"] = "moving"
                response_data: dict[str, Any] = {
                    "success": True,
                    "job_id": job_id,
                    "status": "moving",
                }
                if job.get("identified_title") is not None:
                    response_data["identified_title"] = job["identified_title"]
                if job.get("identified_year") is not None:
                    response_data["identified_year"] = job["identified_year"]
                return JSONResponse(content=response_data)
        return JSONResponse(
            content={"success": False, "error": "Job not found"},
            status_code=404,
        )

    @app.post("/api/jobs/{job_id}/identify")
    async def identify_job(job_id: int, body: IdentifyRequest) -> JSONResponse:
        """Update a job's identification and move to MOVING status.

        Args:
            job_id: The ID of the job to update.
            body: Request body containing title and optional year/tmdb_id.

        Returns:
            JSON response with success status and job details.
        """
        # Use database if available
        if app.state.database is not None:
            from dvdtoplex.database import ContentType, JobStatus

            job = await app.state.database.get_job(job_id)
            if job is None:
                return JSONResponse(
                    content={"detail": "Job not found"},
                    status_code=404,
                )
            if job.status != JobStatus.REVIEW:
                return JSONResponse(
                    content={
                        "detail": f"Job is not in REVIEW status (current: {job.status.value})"
                    },
                    status_code=400,
                )
            # Update identification
            await app.state.database.update_job_identification(
                job_id=job_id,
                content_type=ContentType.MOVIE,  # Default to movie
                title=body.title,
                year=body.year,
                tmdb_id=body.tmdb_id or 0,
                confidence=1.0,  # Manual identification = full confidence
            )
            await app.state.database.update_job_status(job_id, JobStatus.MOVING)
            return JSONResponse(
                content={
                    "success": True,
                    "job_id": job_id,
                    "status": "moving",
                    "identified_title": body.title,
                    "identified_year": body.year,
                    "tmdb_id": body.tmdb_id,
                }
            )

        # Fall back to in-memory state
        for job in app.state.jobs:
            if job.get("id") == job_id:
                # Validate job is in review status
                if job.get("status") != "review":
                    return JSONResponse(
                        content={
                            "success": False,
                            "error": f"Job is not in review status (current: {job.get('status')})",
                        },
                        status_code=400,
                    )
                job["identified_title"] = body.title
                # Preserve existing year if not provided in request
                if body.year is not None:
                    job["identified_year"] = body.year
                # Update tmdb_id if provided
                if body.tmdb_id is not None:
                    job["tmdb_id"] = body.tmdb_id
                job["status"] = "moving"
                response_data: dict[str, Any] = {
                    "success": True,
                    "job_id": job_id,
                    "status": "moving",
                    "identified_title": job["identified_title"],
                }
                if job.get("identified_year") is not None:
                    response_data["identified_year"] = job["identified_year"]
                if job.get("tmdb_id") is not None:
                    response_data["tmdb_id"] = job["tmdb_id"]
                return JSONResponse(content=response_data)
        return JSONResponse(
            content={"success": False, "error": "Job not found"},
            status_code=404,
        )

    @app.post("/api/jobs/{job_id}/pre-identify")
    async def pre_identify_job(job_id: int, body: IdentifyRequest) -> JSONResponse:
        """Pre-identify a job by setting title/year without changing status.

        This allows manual identification of jobs that are still in progress
        (ripping, encoding, etc.) before they reach the REVIEW stage.

        Args:
            job_id: The ID of the job to pre-identify.
            body: Request body containing title and optional year/tmdb_id.

        Returns:
            JSON response with success status and job details.
        """
        # Status values that allow pre-identification (jobs still in progress)
        allowed_statuses = {"pending", "ripping", "ripped", "encoding", "encoded", "identifying"}
        # Status values that do NOT allow pre-identification
        disallowed_statuses = {"review", "moving", "complete", "failed", "archived"}

        # Use database if available
        if app.state.database is not None:
            from dvdtoplex.database import ContentType, JobStatus

            job = await app.state.database.get_job(job_id)
            if job is None:
                return JSONResponse(
                    content={"detail": "Job not found"},
                    status_code=404,
                )

            # Check if job status allows pre-identification
            if job.status.value in disallowed_statuses:
                return JSONResponse(
                    content={
                        "detail": f"Pre-identify not allowed for jobs in {job.status.value.upper()} status"
                    },
                    status_code=400,
                )

            # Search TMDb for additional info (tmdb_id, poster_path)
            tmdb_id = body.tmdb_id
            poster_path = None
            if app.state.config and app.state.config.tmdb_api_token:
                try:
                    from dvdtoplex.tmdb import TMDbClient

                    async with TMDbClient(app.state.config.tmdb_api_token) as tmdb:
                        results = await tmdb.search_movie(body.title, body.year)
                        if results:
                            # Use first result if no tmdb_id provided
                            if tmdb_id is None:
                                tmdb_id = results[0].tmdb_id
                            # Find matching result for poster_path
                            for result in results:
                                if result.tmdb_id == tmdb_id:
                                    poster_path = result.poster_path
                                    break
                            else:
                                # If provided tmdb_id not in results, use first result's poster
                                poster_path = results[0].poster_path
                except Exception as e:
                    logger.warning(f"TMDb search failed during pre-identify: {e}")

            # Update identification without changing status
            await app.state.database.update_job_identification(
                job_id=job_id,
                content_type=ContentType.MOVIE,
                title=body.title,
                year=body.year,
                tmdb_id=tmdb_id or 0,
                confidence=1.0,
                poster_path=poster_path,
            )

            return JSONResponse(
                content={
                    "success": True,
                    "job_id": job_id,
                    "identified_title": body.title,
                    "identified_year": body.year,
                    "tmdb_id": tmdb_id,
                }
            )

        # Fall back to in-memory state
        for job in app.state.jobs:
            if job.get("id") == job_id:
                job_status = job.get("status", "")

                # Check if job status allows pre-identification
                if job_status in disallowed_statuses:
                    return JSONResponse(
                        content={
                            "success": False,
                            "error": f"Pre-identify not allowed for jobs in {job_status} status",
                        },
                        status_code=400,
                    )

                # Update identification fields
                job["identified_title"] = body.title
                if body.year is not None:
                    job["identified_year"] = body.year
                if body.tmdb_id is not None:
                    job["tmdb_id"] = body.tmdb_id
                job["confidence"] = 1.0

                # Status remains unchanged!
                return JSONResponse(
                    content={
                        "success": True,
                        "job_id": job_id,
                        "identified_title": body.title,
                        "identified_year": body.year,
                        "tmdb_id": body.tmdb_id,
                    }
                )

        return JSONResponse(
            content={"success": False, "error": "Job not found"},
            status_code=404,
        )

    @app.post("/api/jobs/{job_id}/skip")
    async def skip_job(job_id: int) -> JSONResponse:
        """Skip a job by marking it as failed.

        Args:
            job_id: The ID of the job to skip.

        Returns:
            JSON response with success status.
        """
        # Use database if available
        if app.state.database is not None:
            from dvdtoplex.database import JobStatus

            logger.info(f"skip_job: Looking up job {job_id} in database")
            job = await app.state.database.get_job(job_id)
            if job is None:
                # Debug: list all jobs in review status
                review_jobs = await app.state.database.get_jobs_by_status(JobStatus.REVIEW)
                job_ids = [j.id for j in review_jobs]
                logger.error(f"skip_job: Job {job_id} not found. Jobs in REVIEW: {job_ids}")
                return JSONResponse(
                    content={"detail": f"Job {job_id} not found. Jobs in REVIEW: {job_ids}"},
                    status_code=404,
                )
            if job.status != JobStatus.REVIEW:
                return JSONResponse(
                    content={
                        "detail": f"Job is not in REVIEW status (current: {job.status.value})"
                    },
                    status_code=400,
                )
            await app.state.database.update_job_status(
                job_id, JobStatus.FAILED, error_message="Skipped by user"
            )
            return JSONResponse(
                content={
                    "success": True,
                    "job_id": job_id,
                    "status": "failed",
                    "error_message": "Skipped by user",
                }
            )

        # Fall back to in-memory state for tests
        for job in app.state.jobs:
            if job.get("id") == job_id:
                # Validate job is in review status
                if job.get("status") != "review":
                    return JSONResponse(
                        content={
                            "success": False,
                            "error": f"Job is not in review status (current: {job.get('status')})",
                        },
                        status_code=400,
                    )
                job["status"] = "failed"
                job["error_message"] = "Skipped by user"
                return JSONResponse(
                    content={
                        "success": True,
                        "job_id": job_id,
                        "status": "failed",
                        "error_message": "Skipped by user",
                    }
                )
        return JSONResponse(
            content={"success": False, "error": "Job not found"},
            status_code=404,
        )

    @app.post("/api/jobs/{job_id}/archive")
    async def archive_job(job_id: int) -> JSONResponse:
        """Archive a completed or failed job to hide from dashboard.

        Args:
            job_id: The ID of the job to archive.

        Returns:
            JSON response with success status.
        """
        if app.state.database is not None:
            from dvdtoplex.database import JobStatus

            job = await app.state.database.get_job(job_id)
            if job is None:
                return JSONResponse(
                    content={"detail": "Job not found"},
                    status_code=404,
                )
            if job.status not in (JobStatus.COMPLETE, JobStatus.FAILED):
                return JSONResponse(
                    content={
                        "detail": f"Can only archive COMPLETE or FAILED jobs (current: {job.status.value})"
                    },
                    status_code=400,
                )
            await app.state.database.update_job_status(job_id, JobStatus.ARCHIVED)
            return JSONResponse(
                content={
                    "success": True,
                    "job_id": job_id,
                    "status": "archived",
                }
            )

        # Fall back to in-memory state
        for job in app.state.jobs:
            if job.get("id") == job_id:
                if job.get("status") not in ("complete", "failed"):
                    return JSONResponse(
                        content={
                            "success": False,
                            "error": f"Can only archive complete or failed jobs (current: {job.get('status')})",
                        },
                        status_code=400,
                    )
                job["status"] = "archived"
                return JSONResponse(
                    content={
                        "success": True,
                        "job_id": job_id,
                        "status": "archived",
                    }
                )
        return JSONResponse(
            content={"success": False, "error": "Job not found"},
            status_code=404,
        )

    # API endpoints for wanted list
    @app.get("/api/wanted")
    async def get_wanted_list() -> JSONResponse:
        """Get all items in the wanted list.

        Returns:
            JSON response with list of wanted items.
        """
        # Use database if available
        if app.state.database is not None:
            db_items = await app.state.database.get_wanted()
            items = [
                {
                    "id": item.id,
                    "title": item.title,
                    "year": item.year,
                    "content_type": item.content_type.value,
                    "tmdb_id": item.tmdb_id,
                    "poster_path": item.poster_path,
                    "notes": item.notes,
                    "added_at": item.added_at.isoformat() if item.added_at else None,
                }
                for item in db_items
            ]
        else:
            items = app.state.wanted

        return JSONResponse(content={"success": True, "items": items})

    @app.post("/api/wanted")
    async def add_wanted(body: WantedRequest) -> JSONResponse:
        """Add an item to the wanted list.

        Automatically enriches items with year and poster_path from TMDb
        if not provided.

        Args:
            body: Request body containing title, year, content_type, tmdb_id, notes.

        Returns:
            JSON response with success status and item details.
        """
        # Validate content_type
        valid_types = {"movie", "tv_season"}
        if body.content_type not in valid_types:
            return JSONResponse(
                content={
                    "success": False,
                    "error": f"Invalid content_type: {body.content_type}",
                },
                status_code=400,
            )

        # Enrich with TMDb data if year or poster_path not provided
        title = body.title
        year = body.year
        tmdb_id = body.tmdb_id
        poster_path = body.poster_path

        if app.state.config and app.state.config.tmdb_api_token:
            # Enrich if missing year, tmdb_id, or poster_path
            if year is None or tmdb_id is None or poster_path is None:
                try:
                    from dvdtoplex.tmdb import TMDbClient

                    async with TMDbClient(app.state.config.tmdb_api_token) as tmdb:
                        if body.content_type == "movie":
                            results = await tmdb.search_movie(title, year)
                        else:
                            results = await tmdb.search_tv(title, year)

                        if results:
                            match = results[0]
                            # Use TMDb data if not provided
                            if body.content_type == "movie":
                                if year is None:
                                    year = match.year
                                if tmdb_id is None:
                                    tmdb_id = match.tmdb_id
                                if poster_path is None:
                                    poster_path = match.poster_path
                                # Use official title from TMDb
                                title = match.title
                            else:
                                if year is None:
                                    year = match.year
                                if tmdb_id is None:
                                    tmdb_id = match.tmdb_id
                                if poster_path is None:
                                    poster_path = match.poster_path
                                title = match.name
                            logger.info(
                                f"Enriched '{body.title}' from TMDb: {title} ({year})"
                            )
                except Exception as e:
                    logger.warning(f"TMDb enrichment failed for '{body.title}': {e}")

        # Use database if available
        if app.state.database is not None:
            from dvdtoplex.database import ContentType

            # Check for duplicate tmdb_id in database
            if tmdb_id is not None:
                existing = await app.state.database.get_wanted()
                for item in existing:
                    if (
                        item.tmdb_id == tmdb_id
                        and item.content_type.value == body.content_type
                    ):
                        return JSONResponse(
                            content={
                                "success": False,
                                "error": f"Item with tmdb_id {tmdb_id} already exists",
                            },
                            status_code=400,
                        )

            # Add to database
            content_type = ContentType(body.content_type)
            new_id = await app.state.database.add_to_wanted(
                title=title,
                year=year,
                content_type=content_type,
                tmdb_id=tmdb_id,
                poster_path=poster_path,
                notes=body.notes,
            )

            return JSONResponse(
                content={
                    "success": True,
                    "id": new_id,
                    "title": title,
                    "year": year,
                    "content_type": body.content_type,
                    "tmdb_id": tmdb_id,
                    "poster_path": poster_path,
                    "notes": body.notes,
                }
            )

        # Fall back to in-memory state
        # Check for duplicate tmdb_id + content_type
        if tmdb_id is not None:
            for item in app.state.wanted:
                if (
                    item.get("tmdb_id") == tmdb_id
                    and item.get("content_type") == body.content_type
                ):
                    return JSONResponse(
                        content={
                            "success": False,
                            "error": f"Item with tmdb_id {tmdb_id} already exists",
                        },
                        status_code=400,
                    )

        # Generate new ID
        if app.state.wanted:
            new_id = max(item.get("id", 0) for item in app.state.wanted) + 1
        else:
            new_id = 1

        # Create the new item
        new_item: dict[str, Any] = {
            "id": new_id,
            "title": title,
            "year": year,
            "content_type": body.content_type,
            "tmdb_id": tmdb_id,
            "poster_path": poster_path,
            "notes": body.notes,
            "added_at": datetime.now().isoformat(),
        }

        # Store in state
        app.state.wanted.append(new_item)

        return JSONResponse(
            content={
                "success": True,
                "id": new_id,
                "title": title,
                "year": year,
                "content_type": body.content_type,
                "tmdb_id": tmdb_id,
                "poster_path": poster_path,
                "notes": body.notes,
            }
        )

    @app.delete("/api/wanted/{item_id}")
    async def delete_wanted(item_id: int) -> JSONResponse:
        """Remove an item from the wanted list.

        Args:
            item_id: The ID of the wanted item to remove.

        Returns:
            JSON response with success status.
        """
        # Use database if available
        if app.state.database is not None:
            removed = await app.state.database.remove_from_wanted(item_id)
            if removed:
                return JSONResponse(
                    content={"success": True, "wanted_id": item_id}
                )
            return JSONResponse(
                content={"success": False, "error": "Wanted item not found"},
                status_code=404,
            )

        # Fall back to in-memory state
        for i, wanted_item in enumerate(app.state.wanted):
            if wanted_item.get("id") == item_id:
                app.state.wanted.pop(i)
                return JSONResponse(
                    content={"success": True, "wanted_id": item_id}
                )
        return JSONResponse(
            content={"success": False, "error": "Wanted item not found"},
            status_code=404,
        )

    # Oversight endpoints for state consistency checking
    @app.get("/api/oversight/check")
    async def check_oversight() -> JSONResponse:
        """Check for state consistency issues."""
        if app.state.database is None:
            return JSONResponse(content={"issues": [], "count": 0})

        from dvdtoplex.services.oversight import check_state_consistency

        issues = await check_state_consistency(app.state.database)
        return JSONResponse(content={"issues": issues, "count": len(issues)})

    @app.post("/api/oversight/fix-encoding")
    async def fix_encoding_issues() -> JSONResponse:
        """Fix multiple encoding jobs by resetting older ones."""
        if app.state.database is None:
            return JSONResponse(
                content={"detail": "Database not available"}, status_code=500
            )

        from dvdtoplex.services.oversight import fix_stuck_encoding_jobs

        fixed_count = await fix_stuck_encoding_jobs(app.state.database)
        return JSONResponse(content={"success": True, "fixed_count": fixed_count})

    # Test endpoints for browser verification (development only)
    @app.post("/api/test/add-job")
    async def add_test_job(request: Request) -> JSONResponse:
        """Add a test job for browser verification.

        Args:
            request: Request object containing job data.

        Returns:
            JSON response with success status.
        """
        data = await request.json()
        app.state.jobs.append(data)
        return JSONResponse(content={"success": True})

    @app.post("/api/test/add-collection")
    async def add_test_collection(request: Request) -> JSONResponse:
        """Add a test collection item for browser verification.

        Args:
            request: Request object containing collection item data.

        Returns:
            JSON response with success status.
        """
        data = await request.json()
        app.state.collection.append(data)
        return JSONResponse(content={"success": True})

    @app.post("/api/test/add-wanted")
    async def add_test_wanted(request: Request) -> JSONResponse:
        """Add a test wanted item for browser verification.

        Args:
            request: Request object containing wanted item data.

        Returns:
            JSON response with success status.
        """
        data = await request.json()
        app.state.wanted.append(data)
        return JSONResponse(content={"success": True})

    return app
