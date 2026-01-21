# PRD: DVD-to-Plex Automated Ripping Pipeline

## Introduction

Build an automated DVD ripping pipeline with two parallel drives, Claude-powered identification, and a web UI for review. The system monitors DVD drives, rips content using MakeMKV, encodes with HandBrake, identifies content via TMDb, and moves completed files to a Plex library. Users receive Pushover notifications and can review uncertain identifications through a web interface.

## Goals

- Automatically detect disc insertion across two parallel DVD drives
- Rip main feature content using MakeMKV
- Encode ripped content using HandBrake with quality settings suitable for Plex
- Identify disc content using TMDb API with confidence scoring
- Auto-approve high-confidence matches, queue low-confidence for manual review
- Move completed encodes to Plex library with proper naming conventions
- Provide web UI for monitoring, review queue, and managing collection/wanted lists
- Send Pushover notifications for completed rips, errors, and review needed
- Run as a macOS launchd service for headless operation

## User Stories

### US-001: Project Structure and Dependencies
**Description:** As a developer, I want to initialize the project with proper structure and dependencies so that development can begin.

**Acceptance Criteria:**
- [x] Create `pyproject.toml` with FastAPI, uvicorn, httpx, python-dotenv, aiosqlite, jinja2, python-multipart dependencies
- [x] Create `src/dvdtoplex/__init__.py` package
- [x] Create `src/dvdtoplex/config.py` with Config dataclass and `load_config()` function
- [x] Create `.env.example` with PUSHOVER_USER_KEY, PUSHOVER_API_TOKEN, TMDB_API_TOKEN, WORKSPACE_DIR, PLEX_MOVIES_DIR, PLEX_TV_DIR, WEB_HOST, WEB_PORT
- [x] Install dependencies with `pip install -e ".[dev]"`
- [x] Typecheck passes

### US-002: Database Schema
**Description:** As a developer, I want a database schema to track jobs, TV seasons, episodes, collection, wanted list, and settings.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/database.py` with JobStatus enum (pending, ripping, ripped, encoding, encoded, identifying, review, moving, complete, failed)
- [x] Create ContentType enum (unknown, movie, tv_season)
- [x] Create Database class with async SQLite operations
- [x] Jobs table with id, drive_id, disc_label, content_type, status, identified_title, identified_year, tmdb_id, confidence, rip_path, encode_path, final_path, error_message, timestamps
- [x] TV seasons, episodes, collection, wanted, settings tables
- [x] Create indexes on jobs(status) and jobs(drive_id)
- [x] Tests in `tests/test_database.py` pass
- [x] Typecheck passes

### US-003: Drive Detection Module
**Description:** As a developer, I want to detect and monitor DVD drive status using macOS drutil.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/drives.py` with DriveStatus dataclass
- [x] Implement `parse_drutil_output()` to extract vendor, has_disc, disc_label
- [x] Implement `get_drive_status()` async function
- [x] Implement `list_dvd_drives()` async function
- [x] Implement `eject_drive()` async function
- [x] Tests in `tests/test_drives.py` pass
- [x] Typecheck passes

### US-004: Drive Watcher Service
**Description:** As a user, I want the system to automatically detect when I insert a DVD so that ripping begins automatically.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/services/drive_watcher.py` with DriveWatcher class
- [x] Poll drives at configurable interval (default 5 seconds)
- [x] Detect disc insertion by tracking state changes
- [x] Create rip job in database when disc is inserted
- [x] Log disc insertions and removals
- [x] Tests in `tests/test_drive_watcher.py` pass
- [x] Typecheck passes

### US-005: MakeMKV Wrapper
**Description:** As a developer, I want a MakeMKV CLI wrapper to get disc info and rip titles.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/makemkv.py` with TitleInfo dataclass
- [x] Implement `parse_duration()` and `parse_size()` helpers
- [x] Implement `parse_title_info()` to extract title index, duration, size, filename from TINFO output
- [x] Implement `get_disc_info()` async function
- [x] Implement `rip_title()` async function with progress callback
- [x] Tests in `tests/test_makemkv.py` pass
- [x] Typecheck passes

### US-006: Rip Queue Service
**Description:** As a user, I want ripping jobs to be processed automatically from both drives in parallel.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/services/rip_queue.py` with RipQueue class
- [x] Implement `select_main_title()` to choose longest title over 60 minutes
- [x] Process pending jobs, one per drive (parallel ripping from both drives)
- [x] Get disc info, select main title, rip to staging directory
- [x] Update job status and rip_path in database
- [x] Eject disc on completion
- [x] Handle errors and update job with error_message
- [x] Tests in `tests/test_rip_queue.py` pass
- [x] Typecheck passes

### US-007: HandBrake Wrapper
**Description:** As a developer, I want a HandBrake CLI wrapper to encode ripped content.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/handbrake.py`
- [x] Implement `build_encode_command()` with x264 encoder, quality 19, high profile, level 4.1, dual audio (passthrough + AAC stereo), subtitle scan
- [x] Implement `encode_file()` async function with progress callback
- [x] Tests in `tests/test_handbrake.py` pass
- [x] Typecheck passes

### US-008: Encode Queue Service
**Description:** As a user, I want ripped content to be automatically encoded one at a time for CPU efficiency.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/services/encode_queue.py` with EncodeQueue class
- [x] Process one job at a time (sequential for CPU efficiency)
- [x] Encode ripped MKV to encoding directory
- [x] Update job status and encode_path in database
- [x] Handle errors and update job with error_message
- [x] Tests in `tests/test_encode_queue.py` pass
- [x] Typecheck passes

### US-009: Pushover Integration
**Description:** As a user, I want to receive mobile notifications about ripping status so I know when to insert the next disc.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/notifications.py` with Notifier class
- [x] Implement `send()` method with title, message, priority, optional URL
- [x] Implement `notify_disc_complete()` helper
- [x] Implement `notify_error()` helper
- [x] Implement `notify_review_needed()` helper with URL to web UI
- [x] Gracefully handle missing credentials (log warning, return False)
- [x] Tests in `tests/test_notifications.py` pass
- [x] Typecheck passes

### US-010: TMDb Client
**Description:** As a developer, I want a TMDb API client to search for movies and TV shows.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/tmdb.py` with MovieMatch and TVMatch dataclasses
- [x] Implement `clean_disc_label()` to remove common patterns (DISC_1, DVD, WIDESCREEN, WS, etc.)
- [x] Implement TMDbClient class with search_movie(), search_tv(), get_movie_details(), get_tv_season()
- [x] Return top 10 results with tmdb_id, title/name, year, overview, poster_path, popularity
- [x] Tests in `tests/test_tmdb.py` pass
- [x] Typecheck passes

### US-011: Identifier Service
**Description:** As a user, I want encoded content to be automatically identified so it can be properly named in Plex.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/services/identifier.py` with IdentifierService class
- [x] Implement `calculate_confidence()` based on title match and popularity
- [x] Auto-approve threshold at 0.85 confidence
- [x] Return IdentificationResult with content_type, title, year, tmdb_id, confidence, needs_review, alternatives
- [x] Process encoded jobs, update with identification, transition to REVIEW or MOVING status
- [x] Tests in `tests/test_identifier.py` pass
- [x] Typecheck passes

### US-012: FastAPI Application Setup
**Description:** As a developer, I want a FastAPI web application structure for the monitoring UI.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/web/` package with `__init__.py` and `app.py`
- [x] Create `create_app()` factory function
- [x] Mount static files directory
- [x] Configure Jinja2 templates
- [x] Add routes: GET / (dashboard), POST /api/active-mode, GET /review, GET /collection, GET /wanted
- [x] Create `templates/base.html` with dark theme, navigation, card/button/status styles
- [x] Typecheck passes

### US-013: Dashboard Template
**Description:** As a user, I want a dashboard showing drive status, active mode toggle, and recent jobs.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/web/templates/dashboard.html`
- [x] Show Active Mode toggle button with ON/OFF state
- [x] Show Drive Status cards for both drives
- [x] Show Recent Jobs table with disc label, status badge, identified title/year, timestamp
- [x] Active mode toggle calls POST /api/active-mode and reloads
- [x] Verify changes work in browser
- [x] Typecheck passes

### US-014: Review Queue Template
**Description:** As a user, I want to review uncertain identifications and approve, edit, or skip them.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/web/templates/review.html`
- [x] Show cards for each job in REVIEW status
- [x] Display disc_label, confidence percentage, best match title/year
- [x] Approve button approves current identification
- [x] Edit button prompts for correct title
- [x] Skip button removes from queue with confirmation
- [x] Verify changes work in browser
- [x] Typecheck passes

### US-015: Collection and Wanted Templates
**Description:** As a user, I want to see my collection and manage a wanted list of titles I'm looking for.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/web/templates/collection.html` with search filter and grid of items
- [x] Create `src/dvdtoplex/web/templates/wanted.html` with search form and item grid
- [x] Collection shows title, year, content type badge
- [x] Collection search filters items client-side
- [x] Wanted shows title, year, notes, remove button
- [x] Wanted search redirects to /wanted/search endpoint
- [x] Verify changes work in browser
- [x] Typecheck passes

### US-016: Main Entry Point
**Description:** As a developer, I want a main entry point that orchestrates all services.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/main.py` with async main() function
- [x] Load config and create workspace directories
- [x] Initialize database
- [x] Create and start DriveWatcher, RipQueue, EncodeQueue, IdentifierService
- [x] Create and start FastAPI app with uvicorn
- [x] Handle SIGTERM/SIGINT for graceful shutdown
- [x] Stop all services and close database on shutdown
- [x] Add `[project.scripts]` entry point `dvdtoplex = "dvdtoplex.main:run"`
- [x] Typecheck passes

### US-017: launchd Service Configuration
**Description:** As a user, I want the system to run as a macOS service on startup.

**Acceptance Criteria:**
- [x] Create `launchd/com.dvdtoplex.service.plist` with Label, ProgramArguments, WorkingDirectory, EnvironmentVariables, RunAtLoad, KeepAlive, stdout/stderr paths
- [x] Create `scripts/install-service.sh` to copy plist, update paths, launchctl load
- [x] Create `scripts/uninstall-service.sh` to launchctl unload and remove plist
- [x] Scripts are executable
- [x] Typecheck passes

### US-018: File Mover Service
**Description:** As a user, I want completed encodes to be automatically moved to my Plex library with proper naming.

**Acceptance Criteria:**
- [x] Create `src/dvdtoplex/services/file_mover.py` with FileMover class
- [x] Implement `sanitize_filename()` to remove invalid characters
- [x] Implement `format_movie_filename()` returning "Title (Year).mkv"
- [x] Implement `format_tv_filename()` returning "Show - S##E## - Title.mkv"
- [x] Move movie to Plex movies dir in "Title (Year)/" folder
- [x] Add to collection table on success
- [x] Clean up job directories (rip and encode) on success
- [x] Handle missing Plex directory gracefully (retry later)
- [x] Tests in `tests/test_file_mover.py` pass
- [x] Typecheck passes

### US-019: Integration Testing
**Description:** As a developer, I want integration tests to verify the full pipeline.

**Acceptance Criteria:**
- [x] Create `tests/integration/test_pipeline.py`
- [x] Test job state transitions through full lifecycle
- [x] Create test fixtures for config and database
- [x] Integration tests pass
- [x] Typecheck passes

### US-020: API Endpoints for Review Actions
**Description:** As a user, I want API endpoints to approve, edit, and skip review items.

**Acceptance Criteria:**
- [x] Add POST /api/jobs/{job_id}/approve endpoint to transition job to MOVING status
- [x] Add POST /api/jobs/{job_id}/identify endpoint to update title and transition to MOVING
- [x] Add POST /api/jobs/{job_id}/skip endpoint to mark job as FAILED with skip reason
- [x] Add DELETE /api/wanted/{id} endpoint to remove from wanted list
- [x] Add POST /api/wanted endpoint to add to wanted list
- [x] Typecheck passes

## Non-Goals

- No Claude Code SDK integration in initial version (identifier uses TMDb only)
- No TV season handling beyond basic schema (focus on movies first)
- No screenshot extraction for identification (ffmpeg integration deferred)
- No subtitle OCR for identification (Tesseract integration deferred)
- No automatic duplicate detection
- No Plex API integration for library refresh
- No support for Blu-ray discs (DVD only)
- No remote access or authentication for web UI
- No concurrent encoding (sequential only for CPU efficiency)

## Technical Considerations

- **Architecture:** Python async services communicating via SQLite, managed by launchd
- **Tech Stack:** Python 3.11+, FastAPI, SQLite (aiosqlite), Jinja2, MakeMKV, HandBrakeCLI
- **External Tools:** drutil (macOS), MakeMKV (/Applications/MakeMKV.app), HandBrakeCLI
- **APIs:** TMDb API (read token), Pushover API
- **Paths:** Workspace at ~/DVDWorkspace, Plex at /Volumes/Media8TB/{Movies,TV Shows}
- **Prerequisites:** Complete `docs/plans/2026-01-17-human-setup.md` for MakeMKV, HandBrake, API keys
