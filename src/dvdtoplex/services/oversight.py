"""State consistency oversight service for detecting impossible states."""

from collections import defaultdict
from datetime import datetime, timedelta

from dvdtoplex.database import Database, Job, JobStatus

# Timeout constants for transient states (in hours)
RIPPING_TIMEOUT_HOURS = 4
ENCODING_TIMEOUT_HOURS = 8
IDENTIFYING_TIMEOUT_HOURS = 1

# Terminal states that should not be checked for issues
TERMINAL_STATES = {JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.ARCHIVED}

# Transient states and their timeout thresholds
TRANSIENT_STATE_TIMEOUTS = {
    JobStatus.RIPPING: RIPPING_TIMEOUT_HOURS,
    JobStatus.ENCODING: ENCODING_TIMEOUT_HOURS,
    JobStatus.IDENTIFYING: IDENTIFYING_TIMEOUT_HOURS,
}


async def check_state_consistency(db: Database) -> list[str]:
    """Check for impossible or problematic states in the job database.

    Checks performed:
    1. Multiple jobs in ENCODING status (only one should encode at a time)
    2. Multiple jobs RIPPING on the same drive (physically impossible)
    3. Jobs stuck in transient states for too long

    Args:
        db: Database instance to check.

    Returns:
        List of issue descriptions. Empty list if no issues found.
    """
    issues: list[str] = []

    all_jobs = await db.get_all_jobs()

    # Filter to active jobs only (not COMPLETE/FAILED/ARCHIVED)
    active_jobs = [job for job in all_jobs if job.status not in TERMINAL_STATES]

    if not active_jobs:
        return issues

    # Check 1: Multiple jobs in ENCODING status
    encoding_jobs = [job for job in active_jobs if job.status == JobStatus.ENCODING]
    if len(encoding_jobs) > 1:
        job_ids = ", ".join(str(job.id) for job in encoding_jobs)
        issues.append(
            f"Multiple jobs in ENCODING status ({len(encoding_jobs)} jobs: {job_ids}). "
            "Only one job should be encoding at a time."
        )

    # Check 2: Multiple jobs RIPPING on same drive
    ripping_by_drive: dict[str, list[Job]] = defaultdict(list)
    for job in active_jobs:
        if job.status == JobStatus.RIPPING:
            ripping_by_drive[job.drive_id].append(job)

    for drive_id, jobs in ripping_by_drive.items():
        if len(jobs) > 1:
            job_ids = ", ".join(str(job.id) for job in jobs)
            issues.append(
                f"Multiple jobs RIPPING on drive {drive_id} ({len(jobs)} jobs: {job_ids}). "
                "Only one job can rip from a drive at a time."
            )

    # Check 3: Jobs stuck in transient states too long
    now = datetime.now()
    for job in active_jobs:
        if job.status in TRANSIENT_STATE_TIMEOUTS:
            timeout_hours = TRANSIENT_STATE_TIMEOUTS[job.status]
            threshold = now - timedelta(hours=timeout_hours)

            if job.updated_at < threshold:
                hours_stuck = (now - job.updated_at).total_seconds() / 3600
                issues.append(
                    f"Job {job.id} appears stuck in {job.status.name} for {hours_stuck:.1f} hours "
                    f"(threshold: {timeout_hours} hours)."
                )

    return issues


async def fix_stuck_encoding_jobs(db: Database) -> int:
    """Reset all but the most recent ENCODING job to RIPPED status.

    When multiple jobs are stuck in ENCODING, this resets the older ones
    back to RIPPED so they can be re-queued for encoding.

    Args:
        db: Database instance to fix.

    Returns:
        Number of jobs that were reset.
    """
    encoding_jobs = await db.get_jobs_by_status(JobStatus.ENCODING)

    if len(encoding_jobs) <= 1:
        return 0

    # Sort by updated_at to find the most recent
    # get_jobs_by_status returns by created_at ASC, we need to re-sort by updated_at DESC
    sorted_jobs = sorted(encoding_jobs, key=lambda j: j.updated_at, reverse=True)

    # Keep the most recent (first in sorted list), reset the rest
    jobs_to_reset = sorted_jobs[1:]
    count = 0

    for job in jobs_to_reset:
        await db.update_job_status(job.id, JobStatus.RIPPED)
        count += 1

    return count
