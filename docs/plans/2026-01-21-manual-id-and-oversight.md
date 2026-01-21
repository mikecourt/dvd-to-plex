# Manual ID & State Oversight Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable manual disc identification before automatic, add state consistency checks to catch impossible states, and clean up stuck jobs on startup.

**Architecture:** Manual ID adds an "Identify" button to dashboard for in-progress jobs that calls the existing identify endpoint. State oversight runs as a periodic task checking for impossible states (multiple ENCODING, stuck jobs). Startup cleanup resets orphaned jobs.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2 templates, aiosqlite, asyncio

---

## Task 1: Add "Identify" Button to Dashboard for In-Progress Jobs

**Files:**
- Modify: `src/dvdtoplex/web/templates/dashboard.html`

**Step 1: Read current dashboard template structure**

Understand where the job rows are rendered and what actions are currently available.

**Step 2: Add Identify button to job rows**

In `src/dvdtoplex/web/templates/dashboard.html`, find the job row actions section and add an Identify button for jobs not yet identified:

```html
<!-- In the actions column, add before archive button -->
{% if job.status in ['pending', 'ripping', 'ripped', 'encoding', 'encoded'] and not job.identified_title %}
<button class="btn btn-sm btn-primary" onclick="identifyJob({{ job.id }}, '{{ job.disc_label | e }}')" title="Identify">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
        <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
    </svg>
</button>
{% endif %}
```

**Step 3: Add identifyJob JavaScript function**

Add to the scripts block:

```javascript
async function identifyJob(jobId, discLabel) {
    // Prompt for title
    const title = prompt('Enter the movie title:', discLabel.replace(/_/g, ' '));
    if (title === null) return;
    if (!title.trim()) {
        alert('Title cannot be empty');
        return;
    }

    // Prompt for year
    const yearStr = prompt('Enter the year (optional):');
    if (yearStr === null) return;

    let year = null;
    if (yearStr.trim()) {
        year = parseInt(yearStr.trim(), 10);
        if (isNaN(year) || year < 1800 || year > 2100) {
            alert('Please enter a valid year between 1800 and 2100');
            return;
        }
    }

    try {
        const response = await fetch(`/api/jobs/${jobId}/pre-identify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: title.trim(), year: year }),
        });

        if (response.ok) {
            window.location.reload();
        } else {
            const data = await response.json();
            alert(data.detail || 'Failed to identify job');
        }
    } catch (error) {
        console.error('Error identifying job:', error);
        alert('Failed to identify job');
    }
}
```

**Step 4: Commit**

```bash
git add src/dvdtoplex/web/templates/dashboard.html && git commit -m "feat: add Identify button to dashboard for in-progress jobs

Allows manual identification of jobs before automatic identification runs.
Button appears for pending/ripping/ripped/encoding/encoded jobs without title.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add Pre-Identify Endpoint

**Files:**
- Modify: `src/dvdtoplex/web/app.py`
- Test: `tests/test_web_preidentify.py` (new)

**Step 1: Write failing test**

Create `tests/test_web_preidentify.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from dvdtoplex.web.app import create_app
from dvdtoplex.database import JobStatus, ContentType
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_preidentify_job_success():
    """Test pre-identify sets title/year without changing status."""
    mock_db = AsyncMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.status = JobStatus.ENCODING
    mock_db.get_job.return_value = mock_job
    mock_db.update_job_identification.return_value = None

    app = create_app(database=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/jobs/1/pre-identify",
            json={"title": "The Matrix", "year": 1999}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["identified_title"] == "The Matrix"
    # Should NOT change status
    mock_db.update_job_status.assert_not_called()


@pytest.mark.asyncio
async def test_preidentify_not_allowed_for_review():
    """Test pre-identify rejects jobs already in REVIEW."""
    mock_db = AsyncMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.status = JobStatus.REVIEW
    mock_job.status.value = "review"
    mock_db.get_job.return_value = mock_job

    app = create_app(database=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/jobs/1/pre-identify",
            json={"title": "The Matrix", "year": 1999}
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_preidentify_not_allowed_for_complete():
    """Test pre-identify rejects completed jobs."""
    mock_db = AsyncMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.status = JobStatus.COMPLETE
    mock_job.status.value = "complete"
    mock_db.get_job.return_value = mock_job

    app = create_app(database=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/jobs/1/pre-identify",
            json={"title": "The Matrix", "year": 1999}
        )

    assert response.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_preidentify.py -v`
Expected: FAIL - endpoint doesn't exist

**Step 3: Add pre-identify endpoint**

In `src/dvdtoplex/web/app.py`, add after the identify endpoint:

```python
@app.post("/api/jobs/{job_id}/pre-identify")
async def pre_identify_job(job_id: int, body: IdentifyRequest) -> JSONResponse:
    """Pre-identify a job before automatic identification runs.

    Sets title/year without changing job status. When the job reaches
    the identifier service, it will skip automatic identification and
    use the pre-set values.

    Args:
        job_id: The ID of the job to pre-identify.
        body: Request body containing title and optional year.

    Returns:
        JSON response with success status.
    """
    if app.state.database is not None:
        from dvdtoplex.database import ContentType, JobStatus

        job = await app.state.database.get_job(job_id)
        if job is None:
            return JSONResponse(
                content={"detail": "Job not found"},
                status_code=404,
            )

        # Only allow pre-identify for jobs not yet in review/moving/complete
        allowed_statuses = {
            JobStatus.PENDING,
            JobStatus.RIPPING,
            JobStatus.RIPPED,
            JobStatus.ENCODING,
            JobStatus.ENCODED,
            JobStatus.IDENTIFYING,
        }
        if job.status not in allowed_statuses:
            return JSONResponse(
                content={
                    "detail": f"Cannot pre-identify job in {job.status.value} status"
                },
                status_code=400,
            )

        # Search TMDb for the title to get tmdb_id and poster
        tmdb_id = 0
        poster_path = None
        try:
            from dvdtoplex.tmdb import TMDbClient
            if app.state.config and app.state.config.tmdb_api_token:
                async with TMDbClient(app.state.config.tmdb_api_token) as client:
                    results = await client.search_movie(body.title, body.year)
                    if results:
                        tmdb_id = results[0].tmdb_id
                        poster_path = results[0].poster_path
        except Exception as e:
            logger.warning(f"TMDb search failed during pre-identify: {e}")

        # Update identification without changing status
        await app.state.database.update_job_identification(
            job_id=job_id,
            content_type=ContentType.MOVIE,
            title=body.title,
            year=body.year,
            tmdb_id=tmdb_id,
            confidence=1.0,  # Manual = full confidence
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

    return JSONResponse(
        content={"detail": "Database not available"},
        status_code=500,
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_preidentify.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/dvdtoplex/web/app.py tests/test_web_preidentify.py && git commit -m "feat: add pre-identify endpoint for manual identification

POST /api/jobs/{id}/pre-identify sets title/year on in-progress jobs
without changing status. Searches TMDb for poster and tmdb_id.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update Identifier to Skip Pre-Identified Jobs

**Files:**
- Modify: `src/dvdtoplex/services/identifier.py`
- Test: `tests/test_identifier.py`

**Step 1: Write failing test**

Add to `tests/test_identifier.py`:

```python
@pytest.mark.asyncio
async def test_identifier_skips_preidentified_jobs(mock_db: MagicMock, mock_config: Config, mock_tmdb: MagicMock) -> None:
    """Pre-identified jobs should skip TMDb search and go straight to MOVING."""
    from datetime import datetime
    from dvdtoplex.database import Job, JobStatus, ContentType

    # Job already has identification from pre-identify
    preidentified_job = Job(
        id=1,
        drive_id="/dev/disk2",
        disc_label="SOME_DISC",
        content_type=ContentType.MOVIE,
        status=JobStatus.ENCODED,
        identified_title="The Matrix",  # Already identified
        identified_year=1999,
        tmdb_id=603,
        confidence=1.0,
        poster_path="/matrix.jpg",
        rip_path="/staging/job_1/movie.mkv",
        encode_path="/encoding/job_1/movie.mkv",
        final_path=None,
        error_message=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    mock_db.get_jobs_by_status.return_value = [preidentified_job]
    mock_db.get_job.return_value = preidentified_job

    service = IdentifierService(db=mock_db, config=mock_config, tmdb_client=mock_tmdb)
    await service._process_encoded_jobs()

    # Should NOT call TMDb search
    mock_tmdb.search_movie.assert_not_called()

    # Should transition directly to MOVING
    calls = mock_db.update_job_status.call_args_list
    assert any(call[0][1] == JobStatus.MOVING for call in calls)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_identifier.py::test_identifier_skips_preidentified_jobs -v`
Expected: FAIL - identifier still searches TMDb

**Step 3: Update identifier to skip pre-identified jobs**

In `src/dvdtoplex/services/identifier.py`, modify `_process_single_job`:

```python
async def _process_single_job(self, job_id: int, disc_label: str) -> None:
    """Process a single identification job."""
    try:
        logger.info(f"Identifying content for {disc_label}")

        # Update status
        await self.db.update_job_status(job_id, JobStatus.IDENTIFYING)

        # Get the job record
        job = await self.db.get_job(job_id)
        if job is None:
            logger.error(f"Job {job_id} not found")
            return

        # Check if already pre-identified (has title and confidence=1.0)
        if job.identified_title and job.confidence == 1.0:
            logger.info(
                f"Job {job_id} already pre-identified as '{job.identified_title}', "
                f"skipping automatic identification"
            )
            await self.db.update_job_status(job_id, JobStatus.MOVING)
            return

        # ... rest of existing identification logic
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_identifier.py::test_identifier_skips_preidentified_jobs -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/dvdtoplex/services/identifier.py tests/test_identifier.py && git commit -m "feat: identifier skips pre-identified jobs

Jobs with confidence=1.0 and existing title skip automatic identification
and transition directly to MOVING status.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add State Consistency Check Function

**Files:**
- Create: `src/dvdtoplex/services/oversight.py`
- Test: `tests/test_oversight.py` (new)

**Step 1: Write failing test**

Create `tests/test_oversight.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta


@pytest.mark.asyncio
async def test_check_multiple_encoding_jobs():
    """Should detect multiple jobs in ENCODING status."""
    from dvdtoplex.services.oversight import check_state_consistency
    from dvdtoplex.database import Job, JobStatus, ContentType

    now = datetime.now()
    jobs = [
        Job(id=1, drive_id="1", disc_label="A", content_type=None, status=JobStatus.ENCODING,
            identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
            poster_path=None, rip_path=None, encode_path=None, final_path=None,
            error_message=None, created_at=now, updated_at=now),
        Job(id=2, drive_id="2", disc_label="B", content_type=None, status=JobStatus.ENCODING,
            identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
            poster_path=None, rip_path=None, encode_path=None, final_path=None,
            error_message=None, created_at=now, updated_at=now),
    ]

    mock_db = AsyncMock()
    mock_db.get_all_jobs.return_value = jobs

    issues = await check_state_consistency(mock_db)

    assert len(issues) >= 1
    assert any("multiple" in issue.lower() and "encoding" in issue.lower() for issue in issues)


@pytest.mark.asyncio
async def test_check_stuck_job():
    """Should detect jobs stuck in transient state too long."""
    from dvdtoplex.services.oversight import check_state_consistency
    from dvdtoplex.database import Job, JobStatus, ContentType

    # Job stuck encoding for 25 hours
    old_time = datetime.now() - timedelta(hours=25)
    jobs = [
        Job(id=1, drive_id="1", disc_label="A", content_type=None, status=JobStatus.ENCODING,
            identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
            poster_path=None, rip_path=None, encode_path=None, final_path=None,
            error_message=None, created_at=old_time, updated_at=old_time),
    ]

    mock_db = AsyncMock()
    mock_db.get_all_jobs.return_value = jobs

    issues = await check_state_consistency(mock_db)

    assert len(issues) >= 1
    assert any("stuck" in issue.lower() for issue in issues)


@pytest.mark.asyncio
async def test_no_issues_normal_state():
    """Should return empty list for valid state."""
    from dvdtoplex.services.oversight import check_state_consistency
    from dvdtoplex.database import Job, JobStatus, ContentType

    now = datetime.now()
    jobs = [
        Job(id=1, drive_id="1", disc_label="A", content_type=None, status=JobStatus.ENCODING,
            identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
            poster_path=None, rip_path=None, encode_path=None, final_path=None,
            error_message=None, created_at=now, updated_at=now),
        Job(id=2, drive_id="2", disc_label="B", content_type=None, status=JobStatus.COMPLETE,
            identified_title=None, identified_year=None, tmdb_id=None, confidence=None,
            poster_path=None, rip_path=None, encode_path=None, final_path=None,
            error_message=None, created_at=now, updated_at=now),
    ]

    mock_db = AsyncMock()
    mock_db.get_all_jobs.return_value = jobs

    issues = await check_state_consistency(mock_db)

    assert len(issues) == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_oversight.py -v`
Expected: FAIL - module doesn't exist

**Step 3: Create oversight module**

Create `src/dvdtoplex/services/oversight.py`:

```python
"""Oversight service for state consistency and self-healing."""

import logging
from datetime import datetime, timedelta
from collections import defaultdict

from dvdtoplex.database import Database, JobStatus

logger = logging.getLogger(__name__)

# Timeouts for stuck job detection
RIPPING_TIMEOUT_HOURS = 4
ENCODING_TIMEOUT_HOURS = 8
IDENTIFYING_TIMEOUT_HOURS = 1


async def check_state_consistency(db: Database) -> list[str]:
    """Check for impossible or problematic states in the job queue.

    Returns:
        List of issue descriptions found.
    """
    issues: list[str] = []

    # Get all non-archived, non-complete, non-failed jobs
    all_jobs = await db.get_all_jobs()
    active_jobs = [
        j for j in all_jobs
        if j.status not in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.ARCHIVED)
    ]

    # Check 1: Multiple jobs in ENCODING (only 1 allowed)
    encoding_jobs = [j for j in active_jobs if j.status == JobStatus.ENCODING]
    if len(encoding_jobs) > 1:
        job_ids = [j.id for j in encoding_jobs]
        issues.append(
            f"Multiple jobs in ENCODING status (only 1 allowed): job IDs {job_ids}"
        )

    # Check 2: Multiple jobs RIPPING on same drive
    ripping_by_drive: dict[str, list[int]] = defaultdict(list)
    for j in active_jobs:
        if j.status == JobStatus.RIPPING:
            ripping_by_drive[j.drive_id].append(j.id)
    for drive_id, job_ids in ripping_by_drive.items():
        if len(job_ids) > 1:
            issues.append(
                f"Multiple jobs RIPPING on drive {drive_id}: job IDs {job_ids}"
            )

    # Check 3: Jobs stuck in transient states too long
    now = datetime.now()
    for job in active_jobs:
        if job.updated_at is None:
            continue

        hours_since_update = (now - job.updated_at).total_seconds() / 3600

        if job.status == JobStatus.RIPPING and hours_since_update > RIPPING_TIMEOUT_HOURS:
            issues.append(
                f"Job {job.id} ({job.disc_label}) stuck in RIPPING for "
                f"{hours_since_update:.1f} hours (timeout: {RIPPING_TIMEOUT_HOURS}h)"
            )
        elif job.status == JobStatus.ENCODING and hours_since_update > ENCODING_TIMEOUT_HOURS:
            issues.append(
                f"Job {job.id} ({job.disc_label}) stuck in ENCODING for "
                f"{hours_since_update:.1f} hours (timeout: {ENCODING_TIMEOUT_HOURS}h)"
            )
        elif job.status == JobStatus.IDENTIFYING and hours_since_update > IDENTIFYING_TIMEOUT_HOURS:
            issues.append(
                f"Job {job.id} ({job.disc_label}) stuck in IDENTIFYING for "
                f"{hours_since_update:.1f} hours (timeout: {IDENTIFYING_TIMEOUT_HOURS}h)"
            )

    return issues


async def fix_stuck_encoding_jobs(db: Database) -> int:
    """Reset all but the most recent ENCODING job to RIPPED status.

    Returns:
        Number of jobs reset.
    """
    all_jobs = await db.get_all_jobs()
    encoding_jobs = [j for j in all_jobs if j.status == JobStatus.ENCODING]

    if len(encoding_jobs) <= 1:
        return 0

    # Sort by updated_at descending, keep the most recent
    encoding_jobs.sort(key=lambda j: j.updated_at or datetime.min, reverse=True)
    jobs_to_reset = encoding_jobs[1:]  # All but the first (most recent)

    for job in jobs_to_reset:
        logger.info(f"Resetting stuck job {job.id} ({job.disc_label}) from ENCODING to RIPPED")
        await db.update_job_status(job.id, JobStatus.RIPPED)

    return len(jobs_to_reset)
```

**Step 4: Add get_all_jobs to Database**

In `src/dvdtoplex/database.py`, add:

```python
async def get_all_jobs(self) -> list[Job]:
    """Get all jobs from the database.

    Returns:
        List of all Job objects.
    """
    async with self._get_connection() as conn:
        cursor = await conn.execute("SELECT * FROM jobs ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_oversight.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/dvdtoplex/services/oversight.py src/dvdtoplex/database.py tests/test_oversight.py && git commit -m "feat: add state consistency check for impossible states

Detects: multiple ENCODING jobs, multiple RIPPING on same drive,
jobs stuck in transient states too long. Includes fix function
to reset stuck encoding jobs.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add Oversight Endpoint to Web UI

**Files:**
- Modify: `src/dvdtoplex/web/app.py`
- Modify: `src/dvdtoplex/web/templates/dashboard.html`

**Step 1: Add oversight check endpoint**

In `src/dvdtoplex/web/app.py`, add:

```python
@app.get("/api/oversight/check")
async def check_oversight() -> JSONResponse:
    """Check for state consistency issues.

    Returns:
        JSON with list of issues found.
    """
    if app.state.database is None:
        return JSONResponse(content={"issues": []})

    from dvdtoplex.services.oversight import check_state_consistency
    issues = await check_state_consistency(app.state.database)

    return JSONResponse(content={"issues": issues, "count": len(issues)})


@app.post("/api/oversight/fix-encoding")
async def fix_encoding_issues() -> JSONResponse:
    """Fix multiple encoding jobs by resetting older ones.

    Returns:
        JSON with number of jobs fixed.
    """
    if app.state.database is None:
        return JSONResponse(
            content={"detail": "Database not available"},
            status_code=500
        )

    from dvdtoplex.services.oversight import fix_stuck_encoding_jobs
    fixed_count = await fix_stuck_encoding_jobs(app.state.database)

    return JSONResponse(content={"success": True, "fixed_count": fixed_count})
```

**Step 2: Add oversight warning to dashboard**

In `src/dvdtoplex/web/templates/dashboard.html`, add after the drive status section:

```html
<!-- Oversight warnings -->
<div id="oversight-warnings" style="display: none; margin-bottom: 1rem;">
    <div class="card" style="border-color: var(--warning); background: rgba(255, 193, 7, 0.1);">
        <div class="card-header" style="color: var(--warning);">
            <span>⚠️ State Issues Detected</span>
        </div>
        <div class="card-body">
            <ul id="oversight-issues" style="margin: 0; padding-left: 1.5rem;"></ul>
            <button class="btn btn-warning" onclick="fixEncodingIssues()" style="margin-top: 0.5rem;">
                Auto-Fix Encoding Issues
            </button>
        </div>
    </div>
</div>
```

**Step 3: Add JavaScript to check oversight on load**

Add to scripts block:

```javascript
// Check for oversight issues on page load
async function checkOversight() {
    try {
        const response = await fetch('/api/oversight/check');
        const data = await response.json();

        if (data.count > 0) {
            const warningsDiv = document.getElementById('oversight-warnings');
            const issuesList = document.getElementById('oversight-issues');

            issuesList.innerHTML = data.issues.map(issue => `<li>${issue}</li>`).join('');
            warningsDiv.style.display = 'block';
        }
    } catch (error) {
        console.error('Error checking oversight:', error);
    }
}

async function fixEncodingIssues() {
    try {
        const response = await fetch('/api/oversight/fix-encoding', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            alert(`Fixed ${data.fixed_count} stuck encoding job(s). Refreshing...`);
            window.location.reload();
        } else {
            alert('Failed to fix issues');
        }
    } catch (error) {
        console.error('Error fixing issues:', error);
        alert('Failed to fix issues');
    }
}

// Run on page load
document.addEventListener('DOMContentLoaded', checkOversight);
```

**Step 4: Commit**

```bash
git add src/dvdtoplex/web/app.py src/dvdtoplex/web/templates/dashboard.html && git commit -m "feat: add oversight check to dashboard UI

Dashboard now shows warning banner when state issues are detected.
Includes auto-fix button for stuck encoding jobs.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Add Startup Cleanup

**Files:**
- Modify: `src/dvdtoplex/main.py`
- Modify: `src/dvdtoplex/services/oversight.py`

**Step 1: Add startup cleanup function**

Add to `src/dvdtoplex/services/oversight.py`:

```python
async def startup_cleanup(db: Database) -> dict[str, int]:
    """Clean up orphaned state on startup.

    Resets jobs stuck in transient states (likely from crash/restart).

    Returns:
        Dict with counts of actions taken.
    """
    results = {"reset_ripping": 0, "reset_encoding": 0, "reset_identifying": 0}

    all_jobs = await db.get_all_jobs()

    for job in all_jobs:
        if job.status == JobStatus.RIPPING:
            logger.info(f"Startup: Resetting stuck RIPPING job {job.id} ({job.disc_label}) to FAILED")
            await db.update_job_status(
                job.id, JobStatus.FAILED, error_message="Reset on startup - was stuck in RIPPING"
            )
            results["reset_ripping"] += 1

        elif job.status == JobStatus.ENCODING:
            # Reset to RIPPED so it can re-encode
            logger.info(f"Startup: Resetting stuck ENCODING job {job.id} ({job.disc_label}) to RIPPED")
            await db.update_job_status(job.id, JobStatus.RIPPED)
            results["reset_encoding"] += 1

        elif job.status == JobStatus.IDENTIFYING:
            # Reset to ENCODED so it can re-identify
            logger.info(f"Startup: Resetting stuck IDENTIFYING job {job.id} ({job.disc_label}) to ENCODED")
            await db.update_job_status(job.id, JobStatus.ENCODED)
            results["reset_identifying"] += 1

    total = sum(results.values())
    if total > 0:
        logger.info(f"Startup cleanup complete: {results}")

    return results
```

**Step 2: Call startup cleanup in main.py**

In `src/dvdtoplex/main.py`, add after database initialization:

```python
# Run startup cleanup
from dvdtoplex.services.oversight import startup_cleanup
cleanup_results = await startup_cleanup(db)
if sum(cleanup_results.values()) > 0:
    logger.info(f"Startup cleanup: {cleanup_results}")
```

**Step 3: Commit**

```bash
git add src/dvdtoplex/services/oversight.py src/dvdtoplex/main.py && git commit -m "feat: add startup cleanup for stuck jobs

On startup, resets jobs stuck in transient states:
- RIPPING -> FAILED (disc likely ejected)
- ENCODING -> RIPPED (will re-encode)
- IDENTIFYING -> ENCODED (will re-identify)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Run Full Test Suite and Verify

**Step 1: Run all tests**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -50
```

**Step 2: Fix any failures**

Address any test failures before proceeding.

**Step 3: Manual verification**

1. Start the app: `python src/dvdtoplex/main.py`
2. Check dashboard shows Identify button for in-progress jobs
3. Test pre-identify on an encoding job
4. Verify oversight warnings appear if there are stuck jobs

**Step 4: Final commit if needed**

```bash
git add -A && git commit -m "fix: address test failures and polish

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan implements:
1. **Manual Disc ID** - Identify button on dashboard, pre-identify endpoint, identifier skips pre-identified jobs
2. **State Consistency Check** - Detects multiple ENCODING, stuck jobs, shows warnings on dashboard
3. **Startup Cleanup** - Resets orphaned jobs on restart

**Not included (for future plans):**
- Dashboard modes (TV/Home Movies/Other)
- Double feature DVD support
- Periodic oversight service (currently on-demand only)
- Disk space monitoring
