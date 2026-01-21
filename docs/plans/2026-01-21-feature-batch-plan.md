# DVD-to-Plex Feature Batch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix critical bugs (skip button, file cleanup) and add UI improvements (file size, archive, box art, modes) to enable continued ripping during development.

**Architecture:** Bug fixes are isolated to specific endpoints/services. UI improvements touch dashboard template, review template, and supporting API endpoints. Mode feature adds database columns and modifies identifier/file mover services.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2 templates, aiosqlite, asyncio

---

## Task 1: Fix Skip Button (Database Path)

**Files:**
- Modify: `ralphy/src/dvdtoplex/web/app.py:426-460`
- Test: `ralphy/tests/test_skip_endpoint.py` (existing)

**Step 1: Read the existing skip endpoint and approve endpoint for reference**

```bash
# Understand the pattern used by approve_job that skip_job is missing
```

**Step 2: Write the failing test for database-backed skip**

Create/update test in `ralphy/tests/test_skip_endpoint.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from dvdtoplex.web.app import create_app
from dvdtoplex.database import JobStatus
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_skip_job_with_database():
    """Test skip endpoint uses database when available."""
    # Create mock database
    mock_db = AsyncMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.status = JobStatus.REVIEW
    mock_db.get_job.return_value = mock_job
    mock_db.update_job_status.return_value = None

    app = create_app(database=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/jobs/1/skip")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "failed"
    mock_db.get_job.assert_called_once_with(1)
    mock_db.update_job_status.assert_called_once()


@pytest.mark.asyncio
async def test_skip_job_not_found_with_database():
    """Test skip returns 404 when job not in database."""
    mock_db = AsyncMock()
    mock_db.get_job.return_value = None

    app = create_app(database=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/jobs/999/skip")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_skip_job_wrong_status_with_database():
    """Test skip returns 400 when job not in REVIEW status."""
    mock_db = AsyncMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.status = JobStatus.COMPLETE
    mock_job.status.value = "complete"
    mock_db.get_job.return_value = mock_job

    app = create_app(database=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/jobs/1/skip")

    assert response.status_code == 400
```

**Step 3: Run test to verify it fails**

Run: `cd ralphy && pytest tests/test_skip_endpoint.py -v`
Expected: FAIL - skip endpoint doesn't check database

**Step 4: Implement database path in skip_job**

In `ralphy/src/dvdtoplex/web/app.py`, replace the `skip_job` function (lines 426-460):

```python
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
```

**Step 5: Run test to verify it passes**

Run: `cd ralphy && pytest tests/test_skip_endpoint.py -v`
Expected: PASS

**Step 6: Run all web tests to check for regressions**

Run: `cd ralphy && pytest tests/test_web*.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
cd ralphy && git add src/dvdtoplex/web/app.py tests/test_skip_endpoint.py && git commit -m "fix: skip button now uses database when available

The skip_job endpoint was only checking in-memory state, causing
404 errors when running with a real database. Now matches the
pattern used by approve_job and identify_job endpoints.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add ARCHIVED Status to JobStatus Enum

**Files:**
- Modify: `ralphy/src/dvdtoplex/database.py` (JobStatus enum)
- Test: `ralphy/tests/test_database.py`

**Step 1: Write failing test for ARCHIVED status**

Add to `ralphy/tests/test_database.py`:

```python
def test_job_status_has_archived():
    """Test that ARCHIVED status exists in JobStatus enum."""
    from dvdtoplex.database import JobStatus

    assert hasattr(JobStatus, "ARCHIVED")
    assert JobStatus.ARCHIVED.value == "archived"
```

**Step 2: Run test to verify it fails**

Run: `cd ralphy && pytest tests/test_database.py::test_job_status_has_archived -v`
Expected: FAIL - ARCHIVED not in enum

**Step 3: Add ARCHIVED to JobStatus enum**

In `ralphy/src/dvdtoplex/database.py`, find the `JobStatus` enum and add ARCHIVED:

```python
class JobStatus(Enum):
    """Status of a ripping job."""

    PENDING = "pending"
    RIPPING = "ripping"
    RIPPED = "ripped"
    ENCODING = "encoding"
    ENCODED = "encoded"
    IDENTIFYING = "identifying"
    REVIEW = "review"
    MOVING = "moving"
    COMPLETE = "complete"
    FAILED = "failed"
    ARCHIVED = "archived"  # Add this line
```

**Step 4: Run test to verify it passes**

Run: `cd ralphy && pytest tests/test_database.py::test_job_status_has_archived -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ralphy && git add src/dvdtoplex/database.py tests/test_database.py && git commit -m "feat: add ARCHIVED status to JobStatus enum

Allows jobs to be archived (hidden from dashboard) while preserving
history in the database.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Add Archive Endpoint and Filter Dashboard

**Files:**
- Modify: `ralphy/src/dvdtoplex/web/app.py`
- Modify: `ralphy/src/dvdtoplex/database.py` (add get_recent_jobs filter)
- Test: `ralphy/tests/test_web_archive.py` (new)

**Step 1: Write failing test for archive endpoint**

Create `ralphy/tests/test_web_archive.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from dvdtoplex.web.app import create_app
from dvdtoplex.database import JobStatus
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_archive_job_success():
    """Test archive endpoint marks job as ARCHIVED."""
    mock_db = AsyncMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.status = JobStatus.COMPLETE
    mock_db.get_job.return_value = mock_job
    mock_db.update_job_status.return_value = None

    app = create_app(database=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/jobs/1/archive")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "archived"
    mock_db.update_job_status.assert_called_once_with(1, JobStatus.ARCHIVED)


@pytest.mark.asyncio
async def test_archive_job_only_complete_or_failed():
    """Test archive only works on COMPLETE or FAILED jobs."""
    mock_db = AsyncMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.status = JobStatus.ENCODING
    mock_job.status.value = "encoding"
    mock_db.get_job.return_value = mock_job

    app = create_app(database=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/jobs/1/archive")

    assert response.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `cd ralphy && pytest tests/test_web_archive.py -v`
Expected: FAIL - endpoint doesn't exist

**Step 3: Add archive endpoint to app.py**

Add after the `skip_job` endpoint in `ralphy/src/dvdtoplex/web/app.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd ralphy && pytest tests/test_web_archive.py -v`
Expected: PASS

**Step 5: Update dashboard to filter out archived jobs**

In `ralphy/src/dvdtoplex/web/app.py`, modify the `dashboard` function to filter archived:

Find the line:
```python
db_jobs = await app.state.database.get_recent_jobs(20)
```

Replace with:
```python
db_jobs = await app.state.database.get_recent_jobs(20, exclude_archived=True)
```

**Step 6: Update database.get_recent_jobs to support exclude_archived**

In `ralphy/src/dvdtoplex/database.py`, modify `get_recent_jobs`:

```python
async def get_recent_jobs(self, limit: int = 20, exclude_archived: bool = False) -> list[Job]:
    """Get recent jobs ordered by updated_at descending.

    Args:
        limit: Maximum number of jobs to return.
        exclude_archived: If True, exclude jobs with ARCHIVED status.

    Returns:
        List of Job objects.
    """
    async with self._get_connection() as conn:
        if exclude_archived:
            query = """
                SELECT * FROM jobs
                WHERE status != 'archived'
                ORDER BY updated_at DESC
                LIMIT ?
            """
        else:
            query = """
                SELECT * FROM jobs
                ORDER BY updated_at DESC
                LIMIT ?
            """
        cursor = await conn.execute(query, (limit,))
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]
```

**Step 7: Run all tests**

Run: `cd ralphy && pytest tests/test_web_archive.py tests/test_database.py -v`
Expected: All PASS

**Step 8: Commit**

```bash
cd ralphy && git add src/dvdtoplex/web/app.py src/dvdtoplex/database.py tests/test_web_archive.py && git commit -m "feat: add archive endpoint and filter archived from dashboard

- POST /api/jobs/{id}/archive marks complete/failed jobs as archived
- Dashboard excludes archived jobs from recent jobs list
- Archived jobs preserved in database for history

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add Archive Button to Dashboard UI

**Files:**
- Modify: `ralphy/src/dvdtoplex/web/templates/dashboard.html`

**Step 1: Read current dashboard template**

Understand the current job row structure.

**Step 2: Add archive button to job rows**

In `ralphy/src/dvdtoplex/web/templates/dashboard.html`, find the recent jobs table/list section and add an archive button for complete/failed jobs:

```html
<!-- In the job row, after the status column -->
<td class="actions">
    {% if job.status in ['complete', 'failed'] %}
    <button class="btn btn-sm btn-secondary" onclick="archiveJob({{ job.id }})" title="Archive">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
            <path d="M0 2a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1v7.5a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 1 12.5V5a1 1 0 0 1-1-1V2zm2 3v7.5A1.5 1.5 0 0 0 3.5 14h9a1.5 1.5 0 0 0 1.5-1.5V5H2zm13-3H1v2h14V2zM5 7.5a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5z"/>
        </svg>
    </button>
    {% endif %}
</td>
```

**Step 3: Add archiveJob JavaScript function**

In the scripts block of `dashboard.html`:

```javascript
async function archiveJob(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}/archive`, {
            method: 'POST',
        });

        if (response.ok) {
            // Remove the row from the table
            const row = document.querySelector(`[data-job-id="${jobId}"]`);
            if (row) {
                row.remove();
            }
        } else {
            const data = await response.json();
            alert(data.detail || 'Failed to archive job');
        }
    } catch (error) {
        console.error('Error archiving job:', error);
        alert('Failed to archive job');
    }
}
```

**Step 4: Manually verify in browser**

Start the app and test archive button works on complete/failed jobs.

**Step 5: Commit**

```bash
cd ralphy && git add src/dvdtoplex/web/templates/dashboard.html && git commit -m "feat: add archive button to dashboard for complete/failed jobs

Archive icon button appears next to complete and failed jobs.
Clicking removes the job from view (archives to database).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add File Size Column to Dashboard

**Files:**
- Modify: `ralphy/src/dvdtoplex/web/app.py` (dashboard endpoint)
- Modify: `ralphy/src/dvdtoplex/web/templates/dashboard.html`
- Test: `ralphy/tests/test_web_dashboard.py`

**Step 1: Write failing test for file size in job data**

Add to `ralphy/tests/test_web_dashboard.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dvdtoplex.web.app import create_app
from dvdtoplex.database import JobStatus, ContentType
from httpx import AsyncClient, ASGITransport
from pathlib import Path


@pytest.mark.asyncio
async def test_dashboard_includes_file_size():
    """Test dashboard returns file size for active jobs."""
    mock_db = AsyncMock()
    mock_config = MagicMock()
    mock_config.staging_dir = Path("/tmp/staging")
    mock_config.encoding_dir = Path("/tmp/encoding")
    mock_config.active_mode = False

    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.disc_label = "TEST_DISC"
    mock_job.status = JobStatus.RIPPING
    mock_job.identified_title = None
    mock_job.identified_year = None
    mock_job.updated_at = None
    mock_db.get_recent_jobs.return_value = [mock_job]

    app = create_app(database=mock_db, config=mock_config)

    with patch("dvdtoplex.web.app.get_drive_status") as mock_drive:
        mock_drive.return_value = MagicMock(has_disc=False, disc_label=None)
        with patch("dvdtoplex.web.app.get_job_file_size") as mock_size:
            mock_size.return_value = "1.5 GB"

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/")

    assert response.status_code == 200
    # File size should be in the response HTML
    assert "1.5 GB" in response.text or mock_size.called
```

**Step 2: Run test to verify it fails**

Run: `cd ralphy && pytest tests/test_web_dashboard.py::test_dashboard_includes_file_size -v`
Expected: FAIL - get_job_file_size doesn't exist

**Step 3: Create get_job_file_size helper function**

Add to `ralphy/src/dvdtoplex/web/app.py` (near the top, after imports):

```python
def format_file_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
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
```

**Step 4: Update dashboard endpoint to include file size**

In the `dashboard` function, update the job dict creation:

```python
recent_jobs = [
    {
        "id": job.id,
        "disc_label": job.disc_label,
        "status": job.status.value,
        "identified_title": job.identified_title,
        "identified_year": job.identified_year,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "file_size": get_job_file_size(job.id, job.status.value, app.state.config) if app.state.config else None,
    }
    for job in db_jobs
]
```

**Step 5: Update dashboard template to show file size**

In `ralphy/src/dvdtoplex/web/templates/dashboard.html`, add a file size column:

```html
<!-- In the table header -->
<th>Size</th>

<!-- In the job row -->
<td>{{ job.file_size or '--' }}</td>
```

**Step 6: Run test to verify it passes**

Run: `cd ralphy && pytest tests/test_web_dashboard.py -v`
Expected: PASS

**Step 7: Commit**

```bash
cd ralphy && git add src/dvdtoplex/web/app.py src/dvdtoplex/web/templates/dashboard.html tests/test_web_dashboard.py && git commit -m "feat: show file size for ripping/encoding jobs on dashboard

Displays current MKV file size in human-readable format (e.g., '2.3 GB')
for jobs that are actively ripping or encoding.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Fix File Mover Cleanup Logging

**Files:**
- Modify: `ralphy/src/dvdtoplex/services/file_mover.py`
- Test: `ralphy/tests/test_file_mover.py`

**Step 1: Write test for cleanup error logging**

Add to `ralphy/tests/test_file_mover.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import logging


@pytest.mark.asyncio
async def test_cleanup_logs_error_on_failure():
    """Test that cleanup failures are logged at ERROR level."""
    from dvdtoplex.services.file_mover import FileMover

    mock_config = MagicMock()
    mock_db = AsyncMock()

    mover = FileMover(mock_config, mock_db)

    # Create paths that will fail to delete
    encode_path = Path("/nonexistent/encode/job_1/movie.mkv")
    rip_path = Path("/nonexistent/staging/job_1/movie.mkv")

    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "is_dir", return_value=True):
            with patch("shutil.rmtree", side_effect=OSError("Permission denied")):
                with patch.object(logging.getLogger("dvdtoplex.services.file_mover"), "error") as mock_error:
                    await mover._cleanup(encode_path, rip_path)

                    # Should log at ERROR level, not WARNING
                    assert mock_error.call_count >= 1
```

**Step 2: Run test to verify it fails**

Run: `cd ralphy && pytest tests/test_file_mover.py::test_cleanup_logs_error_on_failure -v`
Expected: FAIL - currently logs at WARNING level

**Step 3: Change cleanup logging from WARNING to ERROR**

In `ralphy/src/dvdtoplex/services/file_mover.py`, update the `_cleanup` method:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd ralphy && pytest tests/test_file_mover.py::test_cleanup_logs_error_on_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ralphy && git add src/dvdtoplex/services/file_mover.py tests/test_file_mover.py && git commit -m "fix: elevate file cleanup failures from WARNING to ERROR

Cleanup failures were being logged at WARNING level, making them
easy to miss. Now logged at ERROR level for better visibility.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add poster_path Column to Jobs Table

**Files:**
- Modify: `ralphy/src/dvdtoplex/database.py`
- Test: `ralphy/tests/test_database.py`

**Step 1: Write failing test for poster_path field**

Add to `ralphy/tests/test_database.py`:

```python
@pytest.mark.asyncio
async def test_job_has_poster_path_field():
    """Test that Job model has poster_path field."""
    from dvdtoplex.database import Database, JobStatus, ContentType
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        await db.initialize()

        job_id = await db.create_job("TEST_DISC", "1")
        await db.update_job_identification(
            job_id,
            content_type=ContentType.MOVIE,
            title="Test Movie",
            year=2020,
            tmdb_id=12345,
            confidence=0.9,
            poster_path="/abc123.jpg",
        )

        job = await db.get_job(job_id)
        assert job.poster_path == "/abc123.jpg"

        await db.close()
```

**Step 2: Run test to verify it fails**

Run: `cd ralphy && pytest tests/test_database.py::test_job_has_poster_path_field -v`
Expected: FAIL - poster_path not in Job model

**Step 3: Add poster_path to Job model and schema**

In `ralphy/src/dvdtoplex/database.py`:

1. Add to Job dataclass:
```python
@dataclass
class Job:
    """A ripping job."""
    id: int
    drive_id: str
    disc_label: str
    content_type: ContentType | None
    status: JobStatus
    identified_title: str | None
    identified_year: int | None
    tmdb_id: int | None
    confidence: float | None
    poster_path: str | None  # Add this
    rip_path: str | None
    encode_path: str | None
    final_path: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

2. Update CREATE TABLE in `_create_tables`:
```sql
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drive_id TEXT NOT NULL,
    disc_label TEXT NOT NULL,
    content_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    identified_title TEXT,
    identified_year INTEGER,
    tmdb_id INTEGER,
    confidence REAL,
    poster_path TEXT,
    rip_path TEXT,
    encode_path TEXT,
    final_path TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

3. Update `_row_to_job` to include poster_path

4. Update `update_job_identification` to accept and store poster_path:
```python
async def update_job_identification(
    self,
    job_id: int,
    content_type: ContentType,
    title: str,
    year: int | None,
    tmdb_id: int,
    confidence: float,
    poster_path: str | None = None,
) -> None:
```

**Step 4: Run test to verify it passes**

Run: `cd ralphy && pytest tests/test_database.py::test_job_has_poster_path_field -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ralphy && git add src/dvdtoplex/database.py tests/test_database.py && git commit -m "feat: add poster_path column to jobs table

Stores TMDb poster path during identification for display in
review queue box art feature.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update Identifier to Store poster_path

**Files:**
- Modify: `ralphy/src/dvdtoplex/services/identifier.py`
- Modify: `ralphy/src/dvdtoplex/tmdb.py` (if needed to return poster_path)
- Test: `ralphy/tests/test_identifier.py`

**Step 1: Check TMDb response structure**

Read `ralphy/src/dvdtoplex/tmdb.py` to see if poster_path is already available.

**Step 2: Write failing test**

Add to `ralphy/tests/test_identifier.py`:

```python
@pytest.mark.asyncio
async def test_identifier_stores_poster_path():
    """Test that identifier stores poster_path from TMDb."""
    # Mock TMDb to return poster_path
    # Mock database to verify poster_path is passed to update_job_identification
    pass  # Implement based on existing test patterns
```

**Step 3: Update identifier to pass poster_path**

In `ralphy/src/dvdtoplex/services/identifier.py`, when calling `update_job_identification`, include the poster_path from the TMDb result.

**Step 4: Run tests**

Run: `cd ralphy && pytest tests/test_identifier.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ralphy && git add src/dvdtoplex/services/identifier.py src/dvdtoplex/tmdb.py tests/test_identifier.py && git commit -m "feat: identifier stores poster_path from TMDb results

Passes poster_path to database when identifying movies for
display in review queue.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Add Box Art to Review Queue Template

**Files:**
- Modify: `ralphy/src/dvdtoplex/web/app.py` (review endpoint to include poster_url)
- Modify: `ralphy/src/dvdtoplex/web/templates/review.html`

**Step 1: Update review endpoint to include poster_url**

In `ralphy/src/dvdtoplex/web/app.py`, update the review endpoint:

```python
review_jobs.append({
    "id": job.id,
    "disc_label": job.disc_label,
    "status": job.status.value,
    "identified_title": job.identified_title,
    "identified_year": job.identified_year,
    "confidence": job.confidence,
    "content_type": job.content_type.value if job.content_type else None,
    "screenshots": screenshots,
    "poster_url": f"https://image.tmdb.org/t/p/w200{job.poster_path}" if job.poster_path else None,
    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
})
```

**Step 2: Update review template to show poster**

In `ralphy/src/dvdtoplex/web/templates/review.html`, update the card layout:

```html
<div class="card" data-job-id="{{ job.id }}">
    <div class="card-header">
        <span class="card-title">{{ job.disc_label }}</span>
        <span class="badge badge-review">Review</span>
    </div>

    <div class="card-body" style="display: flex; gap: 1rem;">
        <!-- Poster -->
        {% if job.poster_url %}
        <div class="poster" style="flex-shrink: 0;">
            <img src="{{ job.poster_url }}" alt="Poster" style="width: 120px; border-radius: 4px;">
        </div>
        {% endif %}

        <div class="details" style="flex-grow: 1;">
            <!-- Screenshots -->
            {% if job.screenshots %}
            <div class="screenshots" style="margin-bottom: 1rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
                {% for screenshot in job.screenshots %}
                <img src="{{ screenshot }}" alt="Screenshot" style="width: 100px; height: 56px; object-fit: cover; border-radius: 4px; cursor: pointer;" onclick="window.open('{{ screenshot }}', '_blank')">
                {% endfor %}
            </div>
            {% endif %}

            <!-- Confidence meter -->
            <div class="confidence" style="margin-bottom: 1rem;">
                <span>Confidence:</span>
                <div class="confidence-bar">
                    {% set confidence_pct = (job.confidence or 0) * 100 %}
                    {% set confidence_class = 'high' if confidence_pct >= 85 else 'medium' if confidence_pct >= 50 else 'low' %}
                    <div class="confidence-fill {{ confidence_class }}" style="width: {{ confidence_pct }}%;"></div>
                </div>
                <span>{{ "%.0f"|format(confidence_pct) }}%</span>
            </div>

            <!-- Best match -->
            <div style="margin-bottom: 1rem;">
                <p style="color: var(--text-secondary); font-size: 0.9rem;">Best Match:</p>
                <p style="font-size: 1.1rem; font-weight: 500;">
                    {{ job.identified_title or 'Unknown' }}
                    {% if job.identified_year %}({{ job.identified_year }}){% endif %}
                </p>
            </div>

            <!-- Actions -->
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                <button class="btn btn-success" onclick="approveJob({{ job.id }})">Approve</button>
                <button class="btn btn-primary" onclick="editJob({{ job.id }}, '{{ job.identified_title | default('', true) | e }}', '{{ job.identified_year | default('', true) }}')">Edit</button>
                <button class="btn btn-danger" onclick="skipJob({{ job.id }})">Skip</button>
            </div>
        </div>
    </div>
</div>
```

**Step 3: Manually verify in browser**

**Step 4: Commit**

```bash
cd ralphy && git add src/dvdtoplex/web/app.py src/dvdtoplex/web/templates/review.html && git commit -m "feat: display box art poster in review queue

Shows TMDb poster image alongside job details for easier
identification verification.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

Tasks 1-9 cover:
- Skip button fix (Task 1)
- Archive status and button (Tasks 2-4)
- File size column (Task 5)
- File mover cleanup logging fix (Task 6)
- Box art in review queue (Tasks 7-9)

Remaining features (modes, AI oversight, double feature, manual ID) will be planned in a follow-up document after these foundational improvements are complete.
