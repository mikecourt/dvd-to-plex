# DVD-to-Plex Feature Batch Design

## Overview

This document captures the design decisions from our brainstorming session for the next batch of features and bug fixes.

## Priority Order

| # | Feature | Category |
|---|---------|----------|
| 1 | Skip button fix | Bug Fix |
| 2 | File size column in Recent Jobs | UI |
| 3 | Clear/dismiss (Archive) in Recent Jobs | UI |
| 4 | File mover cleanup fix | Bug Fix |
| 5 | Dashboard modes (Movie/TV/Home/Other) | Feature |
| 6 | Box art in review queue | UI |
| 7 | Reset/startup cleanup | Bug Fix |
| 8 | AI self-healing/oversight | Feature |
| 9 | Better DVD matching | Feature |
| 10 | Double feature DVD support | Feature |
| 11 | Manual disc ID before automatic | Feature |

---

## Bug Fixes

### 1. Skip Button Fix

**Problem:** `skip_job` endpoint in `app.py` only uses in-memory `app.state.jobs`, not the database. When running with a real database, jobs are stored in DB, so skip always returns "Job not found" (404).

**Solution:** Add database check matching the pattern used by `approve_job`:
```python
if app.state.database is not None:
    job = await app.state.database.get_job(job_id)
    if job is None:
        return 404
    if job.status != JobStatus.REVIEW:
        return 400
    await app.state.database.update_job_status(job_id, JobStatus.FAILED, error_message="Skipped by user")
    return success
# Fall back to in-memory for tests
```

### 4. File Mover Cleanup Fix

**Problem:** Files aren't being deleted after successful moves. Cleanup failures only log as `warning` level, easy to miss.

**Solution:**
- Elevate cleanup failures to ERROR logging
- Add verification step after cleanup attempt
- Add orphan cleanup utility for manual recovery

### 7. Reset/Startup Cleanup

**Problem:** On system reset/restart, orphaned files and stuck jobs remain.

**Solution:** Add startup task that:
- Finds orphaned job directories in staging/encoding folders
- Resets jobs stuck in transient states (RIPPING, ENCODING) to FAILED
- Cleans up duplicate files from interrupted operations

---

## UI Improvements

### 2. File Size Column

**Location:** Dashboard Recent Jobs list

**Implementation:**
- For jobs in RIPPING status: Check `staging_dir/job_{id}/*.mkv` size
- For jobs in ENCODING status: Check `encoding_dir/job_{id}/*.mkv` size
- Display as human-readable (e.g., "2.3 GB")
- Auto-refresh via JavaScript polling (every 10 seconds)

### 3. Clear/Dismiss (Archive Status)

**Approach:** Add ARCHIVED status to JobStatus enum

**Behavior:**
- Jobs with ARCHIVED status hidden from dashboard
- Archive preserves history in database
- Can be un-archived if needed
- Add "Archive" button to completed/failed jobs in Recent Jobs

### 6. Box Art in Review Queue

**Approach:** Direct TMDb CDN fetch (no local caching needed)

**Implementation:**
- Store `poster_path` from TMDb response during identification (new column)
- Review queue constructs poster URL: `https://image.tmdb.org/t/p/w200/{poster_path}`
- Display poster alongside job card in review queue

**Layout:**
```
┌─────────────────────────────────────┐
│ [Poster]  DISC_LABEL        [Review]│
│ [Image ]  Screenshots: [img][img]   │
│ [120px ]  Confidence: ████░░ 72%    │
│           Best Match:               │
│           The Matrix (1999)         │
│           [Approve] [Edit] [Skip]   │
└─────────────────────────────────────┘
```

---

## Major Features

### 5. Dashboard Modes

**Mode Definitions:**

| Mode | Identification | Output Folder |
|------|----------------|---------------|
| Movie (default) | TMDb movie search | `/Volumes/Media8TB/Movies/` |
| TV | TMDb TV show search | `/Volumes/Media8TB/TV Shows/` |
| Home Movies | Skip TMDb, use disc label | `/Volumes/Media8TB/Home Movies/` |
| Other | Skip TMDb, use disc label | `/Volumes/Media8TB/Other/` |

**Approach:** Global mode toggle with per-disc override in review queue

**UI Changes:**
- Dashboard: Mode selector (4 buttons) below active mode toggle
- Mode persists across sessions (stored in database settings)
- Review queue: Mode override dropdown per job

**Backend Changes:**
- Add `rip_mode` column to Job table
- Add global `current_mode` setting in database
- IdentifierService checks job's mode for identification strategy
- FileMover checks mode for output directory
- Config: Add `plex_home_movies_dir` and `plex_other_dir` paths

### 8. AI Self-Healing/Oversight

**New Service:** `OversightService` running every 5 minutes

**Checks:**

| Check | Trigger | Action |
|-------|---------|--------|
| Stuck ripping | Job in RIPPING > 4 hours | Kill process, mark FAILED, notify |
| Stuck encoding | Job in ENCODING > 8 hours | Kill process, mark FAILED, notify |
| Stale pending | Job in PENDING > 30 min, no drive activity | Log warning, check drive health |
| Idle while active | Active mode ON, no jobs in 30 min, drives ready | Check for drive errors, notify user "ready for next disc" |
| Disk space low | Staging/encoding > 80% full | Notify, pause new rips |

**Configuration:**
```
RIPPING_TIMEOUT_HOURS=4
ENCODING_TIMEOUT_HOURS=8
IDLE_WARNING_MINUTES=30
DISK_SPACE_WARNING_PERCENT=80
```

### 9. Better DVD Matching

**Additional strategies:**
1. Fuzzy disc label parsing - Better heuristics for cleaning labels (remove "DISC1", "WIDESCREEN", etc.)
2. Enhanced AI fallback - More aggressive use of Claude with screenshots

### 10. Double Feature DVDs

**Approach:**
- Detect when MakeMKV rips 2+ feature-length tracks (> 60 min each)
- Flag job as "possible double feature"
- Review queue shows both tracks, user confirms/names each
- Creates two separate jobs from one disc

### 11. Manual Disc ID Before Automatic

**Approach:**
- Jobs in PENDING/RIPPING/RIPPED/ENCODING show "Identify" button in Recent Jobs
- User can pre-fill: title, year, mode
- Pre-identified jobs skip IdentifierService, go straight to MOVING
- If not pre-identified, normal automatic identification runs

**UI:**
```
┌─────────────────────────────────────────────────────────┐
│ DISC_LABEL    encoding    --           2 min ago  [ID] │
│ DISC_LABEL_2  ripping     --           5 min ago  [ID] │
│ Movie Title   complete    Movie (2020) 1 hour ago [✓]  │
└─────────────────────────────────────────────────────────┘
```
