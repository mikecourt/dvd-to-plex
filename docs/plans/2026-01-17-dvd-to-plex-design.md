# DVD-to-Plex Automated Ripping System

**Date:** 2026-01-17
**Status:** Design Complete - Ready for Implementation Planning

## Overview

An automated DVD ripping pipeline that uses two external DVD drives to continuously rip, encode, identify, and organize content into Plex with minimal human intervention. Claude Code serves as the intelligence layer for content identification, error handling, and self-healing.

### Design Goals

- Insert DVD → walk away → content appears in Plex, correctly named
- Both drives ripping in parallel, encoding sequentially
- Claude handles identification, errors, and edge cases autonomously
- Pushover alerts only when genuinely stuck
- Web UI for reviewing uncertain matches and managing collection
- Mobile-friendly wanted list for thrift store hunting
- Active Mode toggle for continuous ripping sessions

---

## System Architecture

### Components

1. **Drive Watcher** - Monitors for DVD insertions/ejections, triggers the pipeline, health checks
2. **Rip Queue** - Manages MakeMKV jobs for both drives in parallel
3. **Encode Queue** - Sequential HandBrake jobs with specified settings
4. **Identifier Service** - Claude Code instance that identifies content, names files, handles errors
5. **Review Web UI** - Local webpage for naming review queue
6. **Collection Tracker** - Mobile-friendly database of owned content + wanted list

### Data Flow

```
DVD inserted → Drive Watcher → Rip Queue → raw MKV in staging
                                              ↓
                              Identifier Service (Claude) analyzes
                                              ↓
                              ┌─ confident → Encode Queue → Plex library → Collection DB (auto-add)
                              └─ uncertain → Review Queue → Web UI → (you approve) → Encode Queue
```

### Directory Structure

```
~/DVDWorkspace/                # Local SSD - fast I/O
├── ripping/                   # MakeMKV output (raw MKVs)
├── encoding/                  # HandBrake output (compressed)
├── staging/                   # Awaiting naming/review
├── logs/                      # System and Claude logs
└── data/                      # SQLite DB, config files

/Volumes/Media8TB/
├── Movies/                    # Plex library (final destination)
└── TV Shows/                  # Plex library (final destination)
```

---

## Content Handling

### Content Types

- **Movies** - Commercial films, one main title per disc
- **TV Series** - Season box sets (Disc 1, Disc 2, etc. within a season)

### Movie Workflow

1. Disc inserted → analyze titles
2. Select longest title with multiple audio tracks
3. **Widescreen/fullscreen detection:**
   - Check video dimensions (720x480 = 4:3 fullscreen, 720x352 or 720x304 = letterboxed widescreen)
   - If known which is widescreen, rip only that
   - If ambiguous, rip both and add to Review Queue
4. Claude identifies movie via APIs + web search
5. If confident → encode and move to Plex
6. If uncertain → Review Queue

### TV Season Workflow

1. First disc detected as TV (multiple 20-45 min titles) → Claude identifies show/season
2. **Pushover prompt:** "Looks like Breaking Bad Season 4. Confirm? How many discs in this season?"
3. User confirms via quick-reply
4. System tracks progress: "Insert Breaking Bad Season 4 disc 2 of 4"
5. All discs rip and encode to season staging folder
6. **Hold for complete season** - nothing moves to Plex yet
7. Once all discs encoded: Claude matches episodes using runtime, disc order, episode count from TMDb
8. If confident → moves to Plex; if uncertain → Review Queue with episode thumbnails

### Title Cleaning (Pre-Matching)

Strips from disc metadata before identification:
- Disc numbers (DISC_1, DVD2)
- Format indicators (WIDESCREEN, FULLSCREEN, WS, FS)
- Region/rating tags (NTSC, RATED_PG)
- Common filler (MOVIE, FEATURE, MAIN_TITLE)

---

## Encoding Settings

- **Codec:** H.264
- **Quality:** RF 19
- **Profile:** High, Level 4.1
- **Framerate:** Same as source, Constant
- **Audio:** Passthru original + AAC stereo fallback
- **Subtitles:** SRT only (OCR via Tesseract to convert DVD bitmap subtitles to text)

### Processing Strategy

- **Parallel rip:** Both drives can rip simultaneously (I/O bound, not CPU bound)
- **Sequential encode:** One encode at a time for quality/speed (CPU bound)
- **Local SSD for speed:** Ripping and encoding on local drive, move to 8TB only after naming

---

## Web UI

### Review Queue (Local Web UI)

Shows pending items needing human decision. For each item displays:

- **Screenshots** - Extracted frames from the actual ripped content
- **Possible matches** - Ranked by confidence score + popularity, each showing:
  - Title, year, poster/DVD box art
  - Match confidence percentage
  - Why it matched (disc label, runtime, episode count, etc.)
- **One-click approve** on any match, or **manual edit** field
- For widescreen/fullscreen situations: shows both rips side-by-side with aspect ratio labeled, pick one to keep

### Collection Tracker (Mobile-Friendly)

- **Owned tab** - Auto-populated from Plex, searchable
- **Wanted tab** - Search TMDb/TVDb to add items, optional notes field
  - Can specify "any season", "Season 2 only", "complete series", etc.
- **At the store:** Search by title → instantly see "Owned", "Wanted", or "Not in lists"

### Dashboard Controls

- **Active Mode toggle** - Enables/disables continuous ripping expectation
- **Pause/Resume** - Stops processing new discs (current jobs finish)
- **Service status** - Shows health of each background service
- **Force restart** - Restarts individual services if stuck
- **Drive status indicators:** 🟢 Ripping / 🟡 Waiting for disc / 🔴 Problem

---

## Claude Code Integration

### How Claude is Embedded

- Identifier Service runs as a persistent background process
- Uses Claude Code SDK to invoke Claude programmatically
- Claude has access to: file system, web search, TMDb/TVDb APIs, MakeMKV/HandBrake logs, disc metadata

### Identification Workflow

1. Receives: disc label, title runtimes, extracted screenshots, any text from disc
2. Cleans title strings (removes DISC_1, WIDESCREEN, etc.)
3. Cross-references web search + multiple APIs for matches
4. Assesses own confidence and decides: auto-proceed or queue for review
5. For TV: coordinates multi-disc season tracking

### Confidence Decisions

Claude decides when to escalate based on:
- Match quality from APIs
- Consistency across multiple sources
- Episode counts matching expectations
- Runtime alignment with known data

---

## Self-Healing & Error Handling

### Active Mode

**ON:** System expects continuous ripping on both drives
- If a drive is idle for >5 minutes with no disc, Pushover: "Drive 1 is empty - insert next disc"
- If a drive has a disc but no mount event, attempts force-mount → alerts if failing
- Dashboard shows drive status in real-time

**OFF:** Passive mode, processes whatever comes but doesn't expect activity
- No "drive is empty" alerts
- Still handles inserted discs normally

### Periodic Health Check (Every 60 Seconds When Active)

- `drutil status` on both drives
- Disc present but not mounted → try `diskutil mount` → try eject/reinsert prompt → alert
- Drive not responding → alert: "Drive 1 not detected - check USB connection"

### Disc Read Errors

- Claude retries with different MakeMKV settings (slower read speed, skip bad sectors)
- If partial rip succeeds (>90% complete), proceeds with warning
- If unrecoverable, ejects disc + Pushover alert: "Disc unreadable - scratched?"

### Encoding Failures

- HandBrake crash → Claude checks logs, restarts job
- If repeated failures → tries fallback settings (lower complexity)
- Logs all attempts for pattern detection

### Identification Failures

- No API matches → Claude tries web search with disc label + runtime
- Still uncertain → Review Queue with "No confident match" flag
- User can manually type the title or skip

### Multi-Disc Edge Cases

- Wrong disc inserted mid-season → Claude detects mismatch, prompts for correct disc
- Disc 3 inserted before disc 2 → Holds in staging, prompts for disc 2
- User abandons mid-season → After 7 days idle, Claude asks via Pushover: "Finish Breaking Bad S4 or cancel?"

### Duplicate Detection

- Before encoding, checks Collection DB for existing title
- If duplicate found → Pushover: "You already have The Matrix (1999). Rip anyway?"

### Drive Issues

- Drive disconnects mid-rip → Pauses job, waits for reconnection, resumes or alerts
- Disc stuck → Sends eject command, alerts if still stuck

### 8TB Drive Unavailable

- Final files held in local staging
- Pushover alert: "Media8TB not mounted - X files waiting to move"
- Auto-moves when drive reconnects

### Escalation to User (via Pushover)

- Only when Claude can't resolve after reasonable attempts
- Message includes: what happened, what Claude tried, what it needs from you
- Links to Review UI if visual confirmation needed

---

## Technology Stack

### Core Tools

| Tool | Purpose |
|------|---------|
| MakeMKV | DVD ripping (need to install `makemkvcon` CLI) |
| HandBrakeCLI | Encoding (already installed) |
| ffmpeg | Screenshot extraction, video analysis (already installed) |
| Tesseract | OCR for subtitle extraction to SRT |

### Application Layer

| Technology | Purpose |
|------------|---------|
| Python 3.11+ | Main orchestration language |
| FastAPI | Web UI backend (Review Queue + Collection Tracker) |
| SQLite | Local database for queue state, collection, wanted list |
| Claude Code SDK | Programmatic Claude invocation for Identifier Service |

### Frontend

- Vanilla HTML/CSS/JS or Alpine.js - Lightweight, no build step
- Mobile-responsive for Collection Tracker
- Local only, no external hosting needed

### Notifications

- Pushover API - Push notifications with quick-reply support

### Process Management

- launchd - macOS native service management (auto-start on boot, restart on crash)

---

## Service Management

### launchd Services (Auto-Start on Boot)

- `com.dvdtoplex.drivewatcher` - Monitors drive events and health checks
- `com.dvdtoplex.ripqueue` - Manages MakeMKV jobs
- `com.dvdtoplex.encodequeue` - Manages HandBrake jobs
- `com.dvdtoplex.identifier` - Claude Code integration service
- `com.dvdtoplex.webui` - FastAPI server (Review Queue + Collection Tracker)

### Startup Behavior

- Services start automatically on Mac boot
- Web UI available at `http://localhost:8080`
- Active Mode defaults to OFF (must enable when starting a ripping session)
- On startup, checks for interrupted jobs in staging and resumes

### Shutdown Behavior

- Finishes current encode before stopping (graceful)
- Incomplete rips marked for re-rip on next start
- TV seasons in progress remembered across restarts

### Remote Access (Optional)

- Tailscale or similar for accessing web UI from phone outside home network
- Pushover works anywhere by default

---

## Hardware Environment

- **Machine:** Mac Mini M1, 16GB RAM (single-purpose)
- **Drives:** Two external USB DVD drives
- **Storage:** 8TB external drive at `/Volumes/Media8TB/`
- **Plex Library Paths:**
  - Movies: `/Volumes/Media8TB/Movies/`
  - TV Shows: `/Volumes/Media8TB/TV Shows/`

---

## Dependencies to Install

- MakeMKV (with `makemkvcon` CLI)
- Tesseract (for subtitle OCR)
- Python packages: FastAPI, uvicorn, httpx, sqlite, pushover client

---

## Next Steps

1. Use this design document as reference for implementation planning
2. Create detailed implementation plan with phases
3. Set up git worktree for isolated development
4. Begin implementation
