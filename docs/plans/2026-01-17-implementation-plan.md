# DVD-to-Plex Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated DVD ripping pipeline with two parallel drives, Claude-powered identification, and a web UI for review.

**Architecture:** Python services communicating via SQLite queues, managed by launchd, with FastAPI web UI. Claude Code SDK handles content identification.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Claude Code SDK, MakeMKV, HandBrakeCLI, ffmpeg, Tesseract

**Prerequisites:** Complete `docs/plans/2026-01-17-human-setup.md` first.

---

## Phase 1: Project Foundation

### Task 1.1: Project Structure and Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `src/dvdtoplex/__init__.py`
- Create: `src/dvdtoplex/config.py`
- Create: `.env.example`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "dvd-to-plex"
version = "0.1.0"
description = "Automated DVD ripping pipeline for Plex"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "httpx>=0.26.0",
    "python-dotenv>=1.0.0",
    "aiosqlite>=0.19.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Create directory structure**

Run:
```bash
mkdir -p src/dvdtoplex tests
touch src/dvdtoplex/__init__.py
```

**Step 3: Create .env.example**

```bash
# DVD-to-Plex Configuration

# Pushover notifications
PUSHOVER_USER_KEY=
PUSHOVER_API_TOKEN=

# TMDb API for content identification
TMDB_API_TOKEN=

# Paths
WORKSPACE_DIR=~/DVDWorkspace
PLEX_MOVIES_DIR=/Volumes/Media8TB/Movies
PLEX_TV_DIR=/Volumes/Media8TB/TV Shows

# Web UI
WEB_HOST=127.0.0.1
WEB_PORT=8080
```

**Step 4: Create config.py**

```python
"""Configuration management for DVD-to-Plex."""

import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration."""

    # Pushover
    pushover_user_key: str
    pushover_api_token: str

    # TMDb
    tmdb_api_token: str

    # Paths
    workspace_dir: Path
    plex_movies_dir: Path
    plex_tv_dir: Path

    # Web UI
    web_host: str
    web_port: int

    @property
    def ripping_dir(self) -> Path:
        return self.workspace_dir / "ripping"

    @property
    def encoding_dir(self) -> Path:
        return self.workspace_dir / "encoding"

    @property
    def staging_dir(self) -> Path:
        return self.workspace_dir / "staging"

    @property
    def logs_dir(self) -> Path:
        return self.workspace_dir / "logs"

    @property
    def data_dir(self) -> Path:
        return self.workspace_dir / "data"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "dvdtoplex.db"


def load_config() -> Config:
    """Load configuration from environment."""
    load_dotenv()

    workspace = Path(os.getenv("WORKSPACE_DIR", "~/DVDWorkspace")).expanduser()

    return Config(
        pushover_user_key=os.getenv("PUSHOVER_USER_KEY", ""),
        pushover_api_token=os.getenv("PUSHOVER_API_TOKEN", ""),
        tmdb_api_token=os.getenv("TMDB_API_TOKEN", ""),
        workspace_dir=workspace,
        plex_movies_dir=Path(os.getenv("PLEX_MOVIES_DIR", "/Volumes/Media8TB/Movies")),
        plex_tv_dir=Path(os.getenv("PLEX_TV_DIR", "/Volumes/Media8TB/TV Shows")),
        web_host=os.getenv("WEB_HOST", "127.0.0.1"),
        web_port=int(os.getenv("WEB_PORT", "8080")),
    )
```

**Step 5: Install dependencies**

Run: `pip install -e ".[dev]"`

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: initialize project structure and configuration"
```

---

### Task 1.2: Database Schema

**Files:**
- Create: `src/dvdtoplex/database.py`
- Create: `tests/test_database.py`

**Step 1: Write failing test**

```python
"""Tests for database module."""

import pytest
from pathlib import Path
from dvdtoplex.database import Database, JobStatus, ContentType


@pytest.fixture
async def db(tmp_path):
    """Create a test database."""
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield db
    await db.close()


async def test_create_rip_job(db):
    """Test creating a rip job."""
    job_id = await db.create_rip_job(
        drive_id="disk2",
        disc_label="THE_MATRIX",
    )
    assert job_id == 1

    job = await db.get_job(job_id)
    assert job["disc_label"] == "THE_MATRIX"
    assert job["status"] == JobStatus.PENDING.value


async def test_update_job_status(db):
    """Test updating job status."""
    job_id = await db.create_rip_job(drive_id="disk2", disc_label="TEST")
    await db.update_job_status(job_id, JobStatus.RIPPING)

    job = await db.get_job(job_id)
    assert job["status"] == JobStatus.RIPPING.value
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py -v`
Expected: FAIL with import error

**Step 3: Write database implementation**

```python
"""Database management for DVD-to-Plex."""

import aiosqlite
from pathlib import Path
from enum import Enum
from typing import Optional
from datetime import datetime


class JobStatus(Enum):
    """Status of a rip/encode job."""
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


class ContentType(Enum):
    """Type of content on disc."""
    UNKNOWN = "unknown"
    MOVIE = "movie"
    TV_SEASON = "tv_season"


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Initialize database connection and schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._create_schema()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()

    async def _create_schema(self) -> None:
        """Create database tables."""
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drive_id TEXT NOT NULL,
                disc_label TEXT,
                content_type TEXT DEFAULT 'unknown',
                status TEXT DEFAULT 'pending',
                identified_title TEXT,
                identified_year INTEGER,
                tmdb_id INTEGER,
                confidence REAL,
                rip_path TEXT,
                encode_path TEXT,
                final_path TEXT,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tv_seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_name TEXT NOT NULL,
                season_number INTEGER NOT NULL,
                total_discs INTEGER,
                discs_ripped INTEGER DEFAULT 0,
                tmdb_id INTEGER,
                status TEXT DEFAULT 'in_progress',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tv_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER REFERENCES tv_seasons(id),
                job_id INTEGER REFERENCES jobs(id),
                episode_number INTEGER,
                title TEXT,
                runtime_seconds INTEGER,
                status TEXT DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS collection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                title TEXT NOT NULL,
                year INTEGER,
                tmdb_id INTEGER,
                file_path TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS wanted (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                title TEXT NOT NULL,
                year INTEGER,
                tmdb_id INTEGER,
                notes TEXT,
                season_spec TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_drive ON jobs(drive_id);
        """)
        await self._conn.commit()

    async def create_rip_job(self, drive_id: str, disc_label: str) -> int:
        """Create a new rip job."""
        cursor = await self._conn.execute(
            "INSERT INTO jobs (drive_id, disc_label) VALUES (?, ?)",
            (drive_id, disc_label)
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_job(self, job_id: int) -> Optional[dict]:
        """Get a job by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_job_status(self, job_id: int, status: JobStatus) -> None:
        """Update job status."""
        await self._conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, datetime.now().isoformat(), job_id)
        )
        await self._conn.commit()

    async def get_pending_rip_jobs(self) -> list[dict]:
        """Get all pending rip jobs."""
        cursor = await self._conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at",
            (JobStatus.PENDING.value,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_pending_encode_jobs(self) -> list[dict]:
        """Get all jobs ready to encode."""
        cursor = await self._conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at",
            (JobStatus.RIPPED.value,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_active_mode(self) -> bool:
        """Get active mode setting."""
        cursor = await self._conn.execute(
            "SELECT value FROM settings WHERE key = 'active_mode'"
        )
        row = await cursor.fetchone()
        return row and row["value"] == "true"

    async def set_active_mode(self, active: bool) -> None:
        """Set active mode."""
        await self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_mode', ?)",
            ("true" if active else "false",)
        )
        await self._conn.commit()
```

**Step 4: Run tests**

Run: `pytest tests/test_database.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add database schema and basic operations"
```

---

## Phase 2: Drive Watcher Service

### Task 2.1: Drive Detection Module

**Files:**
- Create: `src/dvdtoplex/drives.py`
- Create: `tests/test_drives.py`

**Step 1: Write failing test**

```python
"""Tests for drive detection."""

import pytest
from dvdtoplex.drives import parse_drutil_output, DriveStatus


def test_parse_drutil_no_disc():
    """Test parsing drutil output with no disc."""
    output = """Vendor   Product           Rev
    ASUS     DRW-24D5MT        1.00

    Type: No Media Inserted
"""
    status = parse_drutil_output(output)
    assert status.has_disc is False
    assert status.vendor == "ASUS"


def test_parse_drutil_with_disc():
    """Test parsing drutil output with disc inserted."""
    output = """Vendor   Product           Rev
    ASUS     DRW-24D5MT        1.00

    Type: DVD-ROM
    Name: THE_MATRIX
"""
    status = parse_drutil_output(output)
    assert status.has_disc is True
    assert status.disc_label == "THE_MATRIX"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_drives.py -v`
Expected: FAIL with import error

**Step 3: Write implementation**

```python
"""DVD drive detection and management."""

import asyncio
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class DriveStatus:
    """Status of a DVD drive."""
    device_id: str
    vendor: str
    product: str
    has_disc: bool
    disc_label: Optional[str] = None
    disc_type: Optional[str] = None
    mount_point: Optional[str] = None


def parse_drutil_output(output: str) -> DriveStatus:
    """Parse drutil status output."""
    lines = output.strip().split("\n")

    vendor = ""
    product = ""
    has_disc = False
    disc_label = None
    disc_type = None

    for line in lines:
        line = line.strip()

        # Parse vendor/product line (skip header)
        if line and not line.startswith("Vendor") and not line.startswith("Type:") and not line.startswith("Name:"):
            parts = line.split()
            if len(parts) >= 2 and not any(x in line for x in ["Type:", "Name:", "No Media"]):
                vendor = parts[0]
                product = " ".join(parts[1:-1]) if len(parts) > 2 else parts[1]

        if line.startswith("Type:"):
            disc_type = line.split(":", 1)[1].strip()
            has_disc = disc_type != "No Media Inserted"

        if line.startswith("Name:"):
            disc_label = line.split(":", 1)[1].strip()

    return DriveStatus(
        device_id="",  # Set by caller
        vendor=vendor,
        product=product,
        has_disc=has_disc,
        disc_label=disc_label,
        disc_type=disc_type,
    )


async def get_drive_status(device_id: str) -> DriveStatus:
    """Get status of a specific drive."""
    proc = await asyncio.create_subprocess_exec(
        "drutil", "status", "-drive", device_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    status = parse_drutil_output(stdout.decode())
    status.device_id = device_id
    return status


async def list_dvd_drives() -> list[str]:
    """List available DVD drive device IDs."""
    proc = await asyncio.create_subprocess_exec(
        "drutil", "list",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()

    drives = []
    for line in stdout.decode().split("\n"):
        # Look for lines like "        1  Vendor   Product"
        match = re.match(r"\s+(\d+)\s+", line)
        if match:
            drives.append(match.group(1))

    return drives


async def eject_drive(device_id: str) -> bool:
    """Eject a drive."""
    proc = await asyncio.create_subprocess_exec(
        "drutil", "eject", "-drive", device_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0
```

**Step 4: Run tests**

Run: `pytest tests/test_drives.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add drive detection module"
```

---

### Task 2.2: Drive Watcher Service

**Files:**
- Create: `src/dvdtoplex/services/drive_watcher.py`
- Create: `tests/test_drive_watcher.py`

**Step 1: Write failing test**

```python
"""Tests for drive watcher service."""

import pytest
from unittest.mock import AsyncMock, patch
from dvdtoplex.services.drive_watcher import DriveWatcher
from dvdtoplex.drives import DriveStatus


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.create_rip_job = AsyncMock(return_value=1)
    db.get_active_mode = AsyncMock(return_value=True)
    return db


async def test_disc_inserted_creates_job(mock_db):
    """Test that inserting a disc creates a rip job."""
    watcher = DriveWatcher(mock_db, poll_interval=0.1)

    with patch("dvdtoplex.services.drive_watcher.get_drive_status") as mock_status:
        mock_status.return_value = DriveStatus(
            device_id="1",
            vendor="ASUS",
            product="DRW",
            has_disc=True,
            disc_label="THE_MATRIX",
        )

        await watcher._check_drive("1")

        mock_db.create_rip_job.assert_called_once_with(
            drive_id="1",
            disc_label="THE_MATRIX",
        )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_drive_watcher.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""Drive watcher service - monitors DVD drives for disc insertions."""

import asyncio
import logging
from typing import Optional
from dvdtoplex.database import Database
from dvdtoplex.drives import get_drive_status, list_dvd_drives, DriveStatus

logger = logging.getLogger(__name__)


class DriveWatcher:
    """Monitors DVD drives and creates rip jobs when discs are inserted."""

    def __init__(self, db: Database, poll_interval: float = 5.0):
        self.db = db
        self.poll_interval = poll_interval
        self._running = False
        self._drive_states: dict[str, bool] = {}  # drive_id -> has_disc
        self._processing: set[str] = set()  # drives currently being processed

    async def start(self) -> None:
        """Start the drive watcher."""
        self._running = True
        logger.info("Drive watcher started")

        # Initial drive discovery
        drives = await list_dvd_drives()
        for drive_id in drives:
            self._drive_states[drive_id] = False

        logger.info(f"Found {len(drives)} DVD drives: {drives}")

        while self._running:
            await self._poll_drives()
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """Stop the drive watcher."""
        self._running = False
        logger.info("Drive watcher stopped")

    async def _poll_drives(self) -> None:
        """Poll all drives for status changes."""
        for drive_id in list(self._drive_states.keys()):
            try:
                await self._check_drive(drive_id)
            except Exception as e:
                logger.error(f"Error checking drive {drive_id}: {e}")

    async def _check_drive(self, drive_id: str) -> None:
        """Check a single drive for disc insertion."""
        status = await get_drive_status(drive_id)

        previous_has_disc = self._drive_states.get(drive_id, False)

        # Disc was inserted
        if status.has_disc and not previous_has_disc:
            if drive_id not in self._processing:
                await self._handle_disc_inserted(drive_id, status)

        # Disc was removed
        elif not status.has_disc and previous_has_disc:
            self._processing.discard(drive_id)
            logger.info(f"Disc removed from drive {drive_id}")

        self._drive_states[drive_id] = status.has_disc

    async def _handle_disc_inserted(self, drive_id: str, status: DriveStatus) -> None:
        """Handle a newly inserted disc."""
        self._processing.add(drive_id)
        logger.info(f"Disc inserted in drive {drive_id}: {status.disc_label}")

        # Create rip job
        job_id = await self.db.create_rip_job(
            drive_id=drive_id,
            disc_label=status.disc_label or "UNKNOWN",
        )
        logger.info(f"Created rip job {job_id} for disc {status.disc_label}")
```

**Step 4: Create __init__.py for services**

Run: `mkdir -p src/dvdtoplex/services && touch src/dvdtoplex/services/__init__.py`

**Step 5: Run tests**

Run: `pytest tests/test_drive_watcher.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: add drive watcher service"
```

---

## Phase 3: Rip Queue Service

### Task 3.1: MakeMKV Wrapper

**Files:**
- Create: `src/dvdtoplex/makemkv.py`
- Create: `tests/test_makemkv.py`

**Step 1: Write failing test**

```python
"""Tests for MakeMKV wrapper."""

import pytest
from dvdtoplex.makemkv import parse_title_info, TitleInfo


def test_parse_title_info():
    """Test parsing MakeMKV title info output."""
    output = """TINFO:0,9,0,"1:45:32"
TINFO:0,10,0,"6.2 GB"
TINFO:0,27,0,"THE_MATRIX_t00.mkv"
TINFO:1,9,0,"0:02:15"
TINFO:1,10,0,"45 MB"
TINFO:1,27,0,"THE_MATRIX_t01.mkv"
"""
    titles = parse_title_info(output)

    assert len(titles) == 2
    assert titles[0].index == 0
    assert titles[0].duration_seconds == 6332  # 1:45:32
    assert titles[0].size_bytes > 6_000_000_000
    assert titles[1].index == 1
    assert titles[1].duration_seconds == 135  # 0:02:15
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_makemkv.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""MakeMKV CLI wrapper."""

import asyncio
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

MAKEMKV_PATH = "/Applications/MakeMKV.app/Contents/MacOS/makemkvcon"


@dataclass
class TitleInfo:
    """Information about a title on a disc."""
    index: int
    duration_seconds: int
    size_bytes: int
    filename: str
    chapters: int = 0
    audio_tracks: int = 0


def parse_duration(duration_str: str) -> int:
    """Parse duration string like '1:45:32' to seconds."""
    parts = duration_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


def parse_size(size_str: str) -> int:
    """Parse size string like '6.2 GB' to bytes."""
    match = re.match(r"([\d.]+)\s*(GB|MB|KB)", size_str)
    if match:
        value = float(match.group(1))
        unit = match.group(2)
        multipliers = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
        return int(value * multipliers.get(unit, 1))
    return 0


def parse_title_info(output: str) -> list[TitleInfo]:
    """Parse MakeMKV info output into TitleInfo objects."""
    titles: dict[int, dict] = {}

    for line in output.split("\n"):
        if not line.startswith("TINFO:"):
            continue

        # Format: TINFO:title_index,attribute_id,code,value
        match = re.match(r'TINFO:(\d+),(\d+),\d+,"([^"]*)"', line)
        if not match:
            continue

        title_idx = int(match.group(1))
        attr_id = int(match.group(2))
        value = match.group(3)

        if title_idx not in titles:
            titles[title_idx] = {"index": title_idx}

        # Attribute IDs: 9=duration, 10=size, 27=filename
        if attr_id == 9:
            titles[title_idx]["duration"] = parse_duration(value)
        elif attr_id == 10:
            titles[title_idx]["size"] = parse_size(value)
        elif attr_id == 27:
            titles[title_idx]["filename"] = value

    return [
        TitleInfo(
            index=t["index"],
            duration_seconds=t.get("duration", 0),
            size_bytes=t.get("size", 0),
            filename=t.get("filename", f"title_{t['index']}.mkv"),
        )
        for t in titles.values()
    ]


async def get_disc_info(device_id: str) -> list[TitleInfo]:
    """Get information about titles on a disc."""
    proc = await asyncio.create_subprocess_exec(
        MAKEMKV_PATH, "info", f"disc:{device_id}", "-r",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return parse_title_info(stdout.decode())


async def rip_title(
    device_id: str,
    title_index: int,
    output_dir: Path,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Optional[Path]:
    """Rip a specific title from a disc."""
    output_dir.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        MAKEMKV_PATH, "mkv", f"disc:{device_id}", str(title_index), str(output_dir), "-r",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Monitor progress
    while True:
        line = await proc.stdout.readline()
        if not line:
            break

        line = line.decode().strip()
        # Progress lines look like: PRGV:current,total,max
        if line.startswith("PRGV:") and progress_callback:
            parts = line[5:].split(",")
            if len(parts) >= 3:
                current = int(parts[0])
                total = int(parts[2])
                if total > 0:
                    progress_callback(int(current * 100 / total))

    await proc.wait()

    if proc.returncode != 0:
        logger.error(f"MakeMKV failed with return code {proc.returncode}")
        return None

    # Find the output file
    mkv_files = list(output_dir.glob("*.mkv"))
    return mkv_files[0] if mkv_files else None
```

**Step 4: Run tests**

Run: `pytest tests/test_makemkv.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add MakeMKV CLI wrapper"
```

---

### Task 3.2: Rip Queue Service

**Files:**
- Create: `src/dvdtoplex/services/rip_queue.py`
- Create: `tests/test_rip_queue.py`

**Step 1: Write failing test**

```python
"""Tests for rip queue service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
from dvdtoplex.services.rip_queue import RipQueue
from dvdtoplex.database import JobStatus
from dvdtoplex.makemkv import TitleInfo


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.get_pending_rip_jobs = AsyncMock(return_value=[])
    db.update_job_status = AsyncMock()
    return db


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.ripping_dir = Path("/tmp/ripping")
    return config


async def test_selects_main_title():
    """Test that the main movie title is selected."""
    titles = [
        TitleInfo(index=0, duration_seconds=120, size_bytes=1000, filename="t0.mkv"),
        TitleInfo(index=1, duration_seconds=6332, size_bytes=6_000_000_000, filename="t1.mkv"),
        TitleInfo(index=2, duration_seconds=60, size_bytes=500, filename="t2.mkv"),
    ]

    from dvdtoplex.services.rip_queue import select_main_title
    main = select_main_title(titles)

    assert main.index == 1  # Longest title
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_rip_queue.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""Rip queue service - manages MakeMKV ripping jobs."""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from dvdtoplex.database import Database, JobStatus
from dvdtoplex.makemkv import get_disc_info, rip_title, TitleInfo
from dvdtoplex.drives import eject_drive
from dvdtoplex.config import Config

logger = logging.getLogger(__name__)

# Minimum duration for main feature (60 minutes)
MIN_FEATURE_DURATION = 60 * 60


def select_main_title(titles: list[TitleInfo]) -> Optional[TitleInfo]:
    """Select the main title (longest one over minimum duration)."""
    # Filter to titles over minimum duration
    features = [t for t in titles if t.duration_seconds >= MIN_FEATURE_DURATION]

    if not features:
        # Fall back to longest title if none meet minimum
        features = titles

    if not features:
        return None

    # Return longest
    return max(features, key=lambda t: t.duration_seconds)


class RipQueue:
    """Manages parallel ripping jobs from both drives."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config
        self._running = False
        self._active_jobs: dict[str, int] = {}  # drive_id -> job_id

    async def start(self) -> None:
        """Start the rip queue processor."""
        self._running = True
        logger.info("Rip queue started")

        while self._running:
            await self._process_pending_jobs()
            await asyncio.sleep(2.0)

    async def stop(self) -> None:
        """Stop the rip queue processor."""
        self._running = False
        logger.info("Rip queue stopped")

    async def _process_pending_jobs(self) -> None:
        """Process pending rip jobs."""
        pending = await self.db.get_pending_rip_jobs()

        for job in pending:
            drive_id = job["drive_id"]

            # Skip if this drive is already ripping
            if drive_id in self._active_jobs:
                continue

            # Start ripping in background
            asyncio.create_task(self._rip_job(job))

    async def _rip_job(self, job: dict) -> None:
        """Rip a single job."""
        job_id = job["id"]
        drive_id = job["drive_id"]
        disc_label = job["disc_label"]

        self._active_jobs[drive_id] = job_id
        logger.info(f"Starting rip job {job_id} for {disc_label} on drive {drive_id}")

        try:
            await self.db.update_job_status(job_id, JobStatus.RIPPING)

            # Get disc info
            titles = await get_disc_info(drive_id)
            if not titles:
                raise Exception("No titles found on disc")

            # Select main title
            main_title = select_main_title(titles)
            if not main_title:
                raise Exception("Could not determine main title")

            logger.info(f"Selected title {main_title.index} ({main_title.duration_seconds}s)")

            # Rip to staging
            output_dir = self.config.ripping_dir / f"job_{job_id}"
            output_path = await rip_title(
                drive_id,
                main_title.index,
                output_dir,
                progress_callback=lambda p: logger.debug(f"Rip progress: {p}%"),
            )

            if not output_path:
                raise Exception("Ripping failed - no output file")

            # Update job with rip path
            await self.db._conn.execute(
                "UPDATE jobs SET rip_path = ? WHERE id = ?",
                (str(output_path), job_id)
            )
            await self.db._conn.commit()

            await self.db.update_job_status(job_id, JobStatus.RIPPED)
            logger.info(f"Rip complete for job {job_id}: {output_path}")

            # Eject disc
            await eject_drive(drive_id)

        except Exception as e:
            logger.error(f"Rip job {job_id} failed: {e}")
            await self.db._conn.execute(
                "UPDATE jobs SET error_message = ? WHERE id = ?",
                (str(e), job_id)
            )
            await self.db.update_job_status(job_id, JobStatus.FAILED)

        finally:
            del self._active_jobs[drive_id]
```

**Step 4: Run tests**

Run: `pytest tests/test_rip_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add rip queue service"
```

---

## Phase 4: Encode Queue Service

### Task 4.1: HandBrake Wrapper

**Files:**
- Create: `src/dvdtoplex/handbrake.py`
- Create: `tests/test_handbrake.py`

**Step 1: Write failing test**

```python
"""Tests for HandBrake wrapper."""

import pytest
from dvdtoplex.handbrake import build_encode_command
from pathlib import Path


def test_build_encode_command():
    """Test building HandBrake command."""
    cmd = build_encode_command(
        input_path=Path("/tmp/input.mkv"),
        output_path=Path("/tmp/output.mkv"),
    )

    assert "HandBrakeCLI" in cmd[0]
    assert "-i" in cmd
    assert "/tmp/input.mkv" in cmd
    assert "-o" in cmd
    assert "/tmp/output.mkv" in cmd
    assert "--quality" in cmd
    assert "19" in cmd
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_handbrake.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""HandBrake CLI wrapper."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


def build_encode_command(
    input_path: Path,
    output_path: Path,
) -> list[str]:
    """Build HandBrake CLI command with standard settings."""
    return [
        "HandBrakeCLI",
        "-i", str(input_path),
        "-o", str(output_path),
        "--encoder", "x264",
        "--quality", "19",
        "--encoder-profile", "high",
        "--encoder-level", "4.1",
        "--cfr",
        "--audio", "1,1",
        "--aencoder", "copy,av_aac",
        "--mixdown", "none,stereo",
        "--subtitle", "scan",
        "--subtitle-burned", "none",
        "--markers",
    ]


async def encode_file(
    input_path: Path,
    output_path: Path,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> bool:
    """Encode a file using HandBrake."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = build_encode_command(input_path, output_path)
    logger.info(f"Starting encode: {input_path.name}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Monitor progress from stderr
    while True:
        line = await proc.stderr.readline()
        if not line:
            break

        line = line.decode().strip()
        # Progress lines look like: Encoding: task 1 of 1, 45.23 %
        match = re.search(r"(\d+\.\d+)\s*%", line)
        if match and progress_callback:
            progress_callback(int(float(match.group(1))))

    await proc.wait()

    if proc.returncode != 0:
        logger.error(f"HandBrake failed with return code {proc.returncode}")
        return False

    return output_path.exists()
```

**Step 4: Run tests**

Run: `pytest tests/test_handbrake.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add HandBrake CLI wrapper"
```

---

### Task 4.2: Encode Queue Service

**Files:**
- Create: `src/dvdtoplex/services/encode_queue.py`
- Create: `tests/test_encode_queue.py`

**Step 1: Write failing test**

```python
"""Tests for encode queue service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path


async def test_encode_queue_processes_sequentially():
    """Test that encode queue processes one job at a time."""
    from dvdtoplex.services.encode_queue import EncodeQueue

    mock_db = AsyncMock()
    mock_db.get_pending_encode_jobs = AsyncMock(return_value=[])

    mock_config = MagicMock()
    mock_config.encoding_dir = Path("/tmp/encoding")

    queue = EncodeQueue(mock_db, mock_config)
    assert queue._current_job is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_encode_queue.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""Encode queue service - manages sequential HandBrake encoding jobs."""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from dvdtoplex.database import Database, JobStatus
from dvdtoplex.handbrake import encode_file
from dvdtoplex.config import Config

logger = logging.getLogger(__name__)


class EncodeQueue:
    """Manages sequential encoding jobs (one at a time for CPU efficiency)."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config
        self._running = False
        self._current_job: Optional[int] = None

    async def start(self) -> None:
        """Start the encode queue processor."""
        self._running = True
        logger.info("Encode queue started")

        while self._running:
            if self._current_job is None:
                await self._process_next_job()
            await asyncio.sleep(2.0)

    async def stop(self) -> None:
        """Stop the encode queue processor."""
        self._running = False
        logger.info("Encode queue stopped")

    async def _process_next_job(self) -> None:
        """Process the next pending encode job."""
        pending = await self.db.get_pending_encode_jobs()

        if not pending:
            return

        job = pending[0]
        await self._encode_job(job)

    async def _encode_job(self, job: dict) -> None:
        """Encode a single job."""
        job_id = job["id"]
        rip_path = Path(job["rip_path"])
        disc_label = job["disc_label"]

        self._current_job = job_id
        logger.info(f"Starting encode job {job_id} for {disc_label}")

        try:
            await self.db.update_job_status(job_id, JobStatus.ENCODING)

            # Output path
            output_path = self.config.encoding_dir / f"job_{job_id}" / f"{disc_label}.mkv"

            success = await encode_file(
                rip_path,
                output_path,
                progress_callback=lambda p: logger.debug(f"Encode progress: {p}%"),
            )

            if not success:
                raise Exception("Encoding failed")

            # Update job with encode path
            await self.db._conn.execute(
                "UPDATE jobs SET encode_path = ? WHERE id = ?",
                (str(output_path), job_id)
            )
            await self.db._conn.commit()

            await self.db.update_job_status(job_id, JobStatus.ENCODED)
            logger.info(f"Encode complete for job {job_id}: {output_path}")

        except Exception as e:
            logger.error(f"Encode job {job_id} failed: {e}")
            await self.db._conn.execute(
                "UPDATE jobs SET error_message = ? WHERE id = ?",
                (str(e), job_id)
            )
            await self.db.update_job_status(job_id, JobStatus.FAILED)

        finally:
            self._current_job = None
```

**Step 4: Run tests**

Run: `pytest tests/test_encode_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add encode queue service"
```

---

## Phase 5: Notifications

### Task 5.1: Pushover Integration

**Files:**
- Create: `src/dvdtoplex/notifications.py`
- Create: `tests/test_notifications.py`

**Step 1: Write failing test**

```python
"""Tests for notifications."""

import pytest
from unittest.mock import AsyncMock, patch
from dvdtoplex.notifications import Notifier


async def test_send_notification():
    """Test sending a Pushover notification."""
    notifier = Notifier(user_key="test_user", api_token="test_token")

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": 1}
        mock_post.return_value = mock_response

        result = await notifier.send("Test title", "Test message")

        assert result is True
        mock_post.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_notifications.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""Pushover notification integration."""

import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"


class Notifier:
    """Sends notifications via Pushover."""

    def __init__(self, user_key: str, api_token: str):
        self.user_key = user_key
        self.api_token = api_token

    async def send(
        self,
        title: str,
        message: str,
        priority: int = 0,
        url: Optional[str] = None,
        url_title: Optional[str] = None,
    ) -> bool:
        """Send a notification."""
        if not self.user_key or not self.api_token:
            logger.warning("Pushover not configured, skipping notification")
            return False

        data = {
            "token": self.api_token,
            "user": self.user_key,
            "title": title,
            "message": message,
            "priority": priority,
        }

        if url:
            data["url"] = url
        if url_title:
            data["url_title"] = url_title

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(PUSHOVER_API_URL, data=data)

                if response.status_code == 200:
                    logger.info(f"Notification sent: {title}")
                    return True
                else:
                    logger.error(f"Pushover error: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    async def notify_disc_complete(self, title: str, year: Optional[int] = None) -> bool:
        """Notify that a disc has been processed."""
        display = f"{title} ({year})" if year else title
        return await self.send(
            "DVD Complete",
            f"{display} has been ripped and encoded.",
        )

    async def notify_error(self, error: str, context: str = "") -> bool:
        """Notify about an error."""
        return await self.send(
            "DVD-to-Plex Error",
            f"{context}: {error}" if context else error,
            priority=1,
        )

    async def notify_review_needed(self, disc_label: str, url: str) -> bool:
        """Notify that manual review is needed."""
        return await self.send(
            "Review Needed",
            f"Could not identify: {disc_label}",
            url=url,
            url_title="Open Review UI",
        )
```

**Step 4: Run tests**

Run: `pytest tests/test_notifications.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add Pushover notification integration"
```

---

## Phase 6: Content Identification

### Task 6.1: TMDb Client

**Files:**
- Create: `src/dvdtoplex/tmdb.py`
- Create: `tests/test_tmdb.py`

**Step 1: Write failing test**

```python
"""Tests for TMDb client."""

import pytest
from dvdtoplex.tmdb import clean_disc_label


def test_clean_disc_label():
    """Test cleaning disc labels for search."""
    assert clean_disc_label("THE_MATRIX_DISC_1") == "The Matrix"
    assert clean_disc_label("BREAKING_BAD_S4_D2") == "Breaking Bad S4"
    assert clean_disc_label("MOVIE_WIDESCREEN") == "Movie"
    assert clean_disc_label("PULP_FICTION_WS") == "Pulp Fiction"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tmdb.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""TMDb API client for content identification."""

import re
import logging
import httpx
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TMDB_API_BASE = "https://api.themoviedb.org/3"


@dataclass
class MovieMatch:
    """A potential movie match from TMDb."""
    tmdb_id: int
    title: str
    year: int
    overview: str
    poster_path: Optional[str]
    popularity: float
    confidence: float = 0.0


@dataclass
class TVMatch:
    """A potential TV show match from TMDb."""
    tmdb_id: int
    name: str
    first_air_year: int
    overview: str
    poster_path: Optional[str]
    popularity: float
    confidence: float = 0.0


def clean_disc_label(label: str) -> str:
    """Clean a disc label for search queries."""
    # Replace underscores with spaces
    cleaned = label.replace("_", " ")

    # Remove common patterns
    patterns = [
        r"\bDISC\s*\d+\b",
        r"\bDVD\s*\d+\b",
        r"\bD\d+\b",
        r"\bWIDESCREEN\b",
        r"\bFULLSCREEN\b",
        r"\bWS\b",
        r"\bFS\b",
        r"\bNTSC\b",
        r"\bPAL\b",
        r"\bRATED\s*\w+\b",
        r"\bMOVIE\b$",
        r"\bFEATURE\b",
        r"\bMAIN\s*TITLE\b",
    ]

    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Clean up whitespace
    cleaned = " ".join(cleaned.split())

    # Title case
    return cleaned.title()


class TMDbClient:
    """Client for TMDb API."""

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "accept": "application/json",
        }

    async def search_movie(self, query: str, year: Optional[int] = None) -> list[MovieMatch]:
        """Search for movies."""
        params = {"query": query}
        if year:
            params["year"] = year

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TMDB_API_BASE}/search/movie",
                headers=self.headers,
                params=params,
            )

            if response.status_code != 200:
                logger.error(f"TMDb search failed: {response.text}")
                return []

            data = response.json()
            results = []

            for item in data.get("results", [])[:10]:
                release_year = 0
                if item.get("release_date"):
                    try:
                        release_year = int(item["release_date"][:4])
                    except (ValueError, IndexError):
                        pass

                results.append(MovieMatch(
                    tmdb_id=item["id"],
                    title=item["title"],
                    year=release_year,
                    overview=item.get("overview", ""),
                    poster_path=item.get("poster_path"),
                    popularity=item.get("popularity", 0),
                ))

            return results

    async def search_tv(self, query: str) -> list[TVMatch]:
        """Search for TV shows."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TMDB_API_BASE}/search/tv",
                headers=self.headers,
                params={"query": query},
            )

            if response.status_code != 200:
                logger.error(f"TMDb search failed: {response.text}")
                return []

            data = response.json()
            results = []

            for item in data.get("results", [])[:10]:
                first_year = 0
                if item.get("first_air_date"):
                    try:
                        first_year = int(item["first_air_date"][:4])
                    except (ValueError, IndexError):
                        pass

                results.append(TVMatch(
                    tmdb_id=item["id"],
                    name=item["name"],
                    first_air_year=first_year,
                    overview=item.get("overview", ""),
                    poster_path=item.get("poster_path"),
                    popularity=item.get("popularity", 0),
                ))

            return results

    async def get_movie_details(self, tmdb_id: int) -> Optional[dict]:
        """Get detailed movie information."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TMDB_API_BASE}/movie/{tmdb_id}",
                headers=self.headers,
            )

            if response.status_code == 200:
                return response.json()
            return None

    async def get_tv_season(self, tmdb_id: int, season: int) -> Optional[dict]:
        """Get TV season details including episodes."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TMDB_API_BASE}/tv/{tmdb_id}/season/{season}",
                headers=self.headers,
            )

            if response.status_code == 200:
                return response.json()
            return None
```

**Step 4: Run tests**

Run: `pytest tests/test_tmdb.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add TMDb API client"
```

---

### Task 6.2: Identifier Service

**Files:**
- Create: `src/dvdtoplex/services/identifier.py`
- Create: `tests/test_identifier.py`

**Step 1: Write failing test**

```python
"""Tests for identifier service."""

import pytest
from dvdtoplex.services.identifier import calculate_confidence


def test_calculate_confidence_exact_match():
    """Test confidence for exact title match."""
    confidence = calculate_confidence(
        query="The Matrix",
        result_title="The Matrix",
        popularity=100,
    )
    assert confidence >= 0.9


def test_calculate_confidence_partial_match():
    """Test confidence for partial match."""
    confidence = calculate_confidence(
        query="Matrix",
        result_title="The Matrix",
        popularity=100,
    )
    assert 0.5 <= confidence < 0.9
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_identifier.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""Identifier service - uses Claude and TMDb to identify content."""

import logging
from typing import Optional
from dataclasses import dataclass
from dvdtoplex.database import Database, JobStatus, ContentType
from dvdtoplex.tmdb import TMDbClient, clean_disc_label, MovieMatch
from dvdtoplex.config import Config

logger = logging.getLogger(__name__)

# Confidence threshold for auto-approval
AUTO_APPROVE_THRESHOLD = 0.85


def calculate_confidence(query: str, result_title: str, popularity: float) -> float:
    """Calculate match confidence score."""
    query_lower = query.lower()
    result_lower = result_title.lower()

    # Exact match
    if query_lower == result_lower:
        return min(0.95, 0.8 + (popularity / 1000))

    # Query is substring of result or vice versa
    if query_lower in result_lower or result_lower in query_lower:
        return min(0.85, 0.6 + (popularity / 1000))

    # Word overlap
    query_words = set(query_lower.split())
    result_words = set(result_lower.split())
    overlap = len(query_words & result_words)
    total = len(query_words | result_words)

    if total > 0:
        jaccard = overlap / total
        return min(0.75, jaccard * 0.7 + (popularity / 2000))

    return 0.3


@dataclass
class IdentificationResult:
    """Result of content identification."""
    content_type: ContentType
    title: str
    year: Optional[int]
    tmdb_id: Optional[int]
    confidence: float
    needs_review: bool
    alternatives: list[MovieMatch]


class IdentifierService:
    """Identifies disc content using TMDb and Claude."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config
        self.tmdb = TMDbClient(config.tmdb_api_token)

    async def start(self) -> None:
        """Start the identifier service."""
        logger.info("Identifier service started")

    async def stop(self) -> None:
        """Stop the identifier service."""
        logger.info("Identifier service stopped")

    async def identify(self, job_id: int) -> IdentificationResult:
        """Identify content for a job."""
        job = await self.db.get_job(job_id)
        disc_label = job["disc_label"]

        logger.info(f"Identifying job {job_id}: {disc_label}")

        # Clean the disc label
        search_query = clean_disc_label(disc_label)
        logger.info(f"Cleaned query: {search_query}")

        # Search TMDb for movies
        movie_results = await self.tmdb.search_movie(search_query)

        if not movie_results:
            return IdentificationResult(
                content_type=ContentType.UNKNOWN,
                title=search_query,
                year=None,
                tmdb_id=None,
                confidence=0.0,
                needs_review=True,
                alternatives=[],
            )

        # Calculate confidence for each result
        for result in movie_results:
            result.confidence = calculate_confidence(
                search_query,
                result.title,
                result.popularity,
            )

        # Sort by confidence
        movie_results.sort(key=lambda x: x.confidence, reverse=True)
        best_match = movie_results[0]

        needs_review = best_match.confidence < AUTO_APPROVE_THRESHOLD

        return IdentificationResult(
            content_type=ContentType.MOVIE,
            title=best_match.title,
            year=best_match.year,
            tmdb_id=best_match.tmdb_id,
            confidence=best_match.confidence,
            needs_review=needs_review,
            alternatives=movie_results[1:5],
        )

    async def process_encoded_jobs(self) -> None:
        """Process jobs that have finished encoding and need identification."""
        cursor = await self.db._conn.execute(
            "SELECT * FROM jobs WHERE status = ?",
            (JobStatus.ENCODED.value,)
        )
        rows = await cursor.fetchall()

        for row in rows:
            job = dict(row)
            await self.db.update_job_status(job["id"], JobStatus.IDENTIFYING)

            result = await self.identify(job["id"])

            # Update job with identification
            await self.db._conn.execute("""
                UPDATE jobs SET
                    content_type = ?,
                    identified_title = ?,
                    identified_year = ?,
                    tmdb_id = ?,
                    confidence = ?
                WHERE id = ?
            """, (
                result.content_type.value,
                result.title,
                result.year,
                result.tmdb_id,
                result.confidence,
                job["id"],
            ))
            await self.db._conn.commit()

            if result.needs_review:
                await self.db.update_job_status(job["id"], JobStatus.REVIEW)
                logger.info(f"Job {job['id']} needs review (confidence: {result.confidence:.2f})")
            else:
                # Auto-approved, move to moving state
                await self.db.update_job_status(job["id"], JobStatus.MOVING)
                logger.info(f"Job {job['id']} auto-approved: {result.title} ({result.year})")
```

**Step 4: Run tests**

Run: `pytest tests/test_identifier.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add identifier service with TMDb integration"
```

---

## Phase 7: Web UI

### Task 7.1: FastAPI Application Setup

**Files:**
- Create: `src/dvdtoplex/web/__init__.py`
- Create: `src/dvdtoplex/web/app.py`
- Create: `src/dvdtoplex/web/templates/base.html`

**Step 1: Create web package**

Run: `mkdir -p src/dvdtoplex/web/templates src/dvdtoplex/web/static`

**Step 2: Create base template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}DVD-to-Plex{% endblock %}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header {
            background: #16213e;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 { font-size: 1.5rem; }
        nav a {
            color: #eee;
            text-decoration: none;
            margin-left: 20px;
            padding: 8px 16px;
            border-radius: 4px;
            transition: background 0.2s;
        }
        nav a:hover { background: #0f3460; }
        nav a.active { background: #e94560; }
        .card {
            background: #16213e;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .btn {
            background: #e94560;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
        }
        .btn:hover { background: #d63050; }
        .btn-secondary { background: #0f3460; }
        .btn-secondary:hover { background: #1a4a7a; }
        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85rem;
        }
        .status-ripping { background: #f39c12; color: #000; }
        .status-encoding { background: #3498db; }
        .status-review { background: #e94560; }
        .status-complete { background: #27ae60; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
    <header>
        <h1>DVD-to-Plex</h1>
        <nav>
            <a href="/" {% if active_page == 'dashboard' %}class="active"{% endif %}>Dashboard</a>
            <a href="/review" {% if active_page == 'review' %}class="active"{% endif %}>Review</a>
            <a href="/collection" {% if active_page == 'collection' %}class="active"{% endif %}>Collection</a>
            <a href="/wanted" {% if active_page == 'wanted' %}class="active"{% endif %}>Wanted</a>
        </nav>
    </header>
    <main class="container">
        {% block content %}{% endblock %}
    </main>
    {% block scripts %}{% endblock %}
</body>
</html>
```

**Step 3: Create FastAPI app**

```python
"""FastAPI web application for DVD-to-Plex."""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dvdtoplex.database import Database
from dvdtoplex.config import Config

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app(db: Database, config: Config) -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(title="DVD-to-Plex")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def dashboard(request: Request):
        """Dashboard page."""
        active_mode = await db.get_active_mode()

        # Get recent jobs
        cursor = await db._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 20"
        )
        rows = await cursor.fetchall()
        jobs = [dict(row) for row in rows]

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "active_page": "dashboard",
            "active_mode": active_mode,
            "jobs": jobs,
        })

    @app.post("/api/active-mode")
    async def toggle_active_mode():
        """Toggle active mode."""
        current = await db.get_active_mode()
        await db.set_active_mode(not current)
        return {"active_mode": not current}

    @app.get("/review")
    async def review_queue(request: Request):
        """Review queue page."""
        cursor = await db._conn.execute(
            "SELECT * FROM jobs WHERE status = 'review' ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        jobs = [dict(row) for row in rows]

        return templates.TemplateResponse("review.html", {
            "request": request,
            "active_page": "review",
            "jobs": jobs,
        })

    @app.get("/collection")
    async def collection(request: Request):
        """Collection page."""
        cursor = await db._conn.execute(
            "SELECT * FROM collection ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
        items = [dict(row) for row in rows]

        return templates.TemplateResponse("collection.html", {
            "request": request,
            "active_page": "collection",
            "items": items,
        })

    @app.get("/wanted")
    async def wanted(request: Request):
        """Wanted list page."""
        cursor = await db._conn.execute(
            "SELECT * FROM wanted ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
        items = [dict(row) for row in rows]

        return templates.TemplateResponse("wanted.html", {
            "request": request,
            "active_page": "wanted",
            "items": items,
        })

    return app
```

**Step 4: Create __init__.py**

```python
"""Web UI package."""
from .app import create_app

__all__ = ["create_app"]
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add FastAPI web application setup"
```

---

### Task 7.2: Dashboard Template

**Files:**
- Create: `src/dvdtoplex/web/templates/dashboard.html`

**Step 1: Create dashboard template**

```html
{% extends "base.html" %}

{% block title %}Dashboard - DVD-to-Plex{% endblock %}

{% block content %}
<h2 style="margin-bottom: 20px;">Dashboard</h2>

<div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h3>Active Mode</h3>
            <p style="color: #888; margin-top: 5px;">
                {% if active_mode %}
                System expects continuous ripping
                {% else %}
                Passive mode - processes discs when inserted
                {% endif %}
            </p>
        </div>
        <button id="active-toggle" class="btn {% if not active_mode %}btn-secondary{% endif %}">
            {{ "ON" if active_mode else "OFF" }}
        </button>
    </div>
</div>

<div class="card">
    <h3 style="margin-bottom: 15px;">Drive Status</h3>
    <div class="grid">
        <div style="background: #1a1a2e; padding: 15px; border-radius: 4px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.5rem;">🟡</span>
                <div>
                    <strong>Drive 1</strong>
                    <p style="color: #888; font-size: 0.9rem;">Waiting for disc</p>
                </div>
            </div>
        </div>
        <div style="background: #1a1a2e; padding: 15px; border-radius: 4px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.5rem;">🟡</span>
                <div>
                    <strong>Drive 2</strong>
                    <p style="color: #888; font-size: 0.9rem;">Waiting for disc</p>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="card">
    <h3 style="margin-bottom: 15px;">Recent Jobs</h3>
    {% if jobs %}
    <table style="width: 100%; border-collapse: collapse;">
        <thead>
            <tr style="text-align: left; border-bottom: 1px solid #333;">
                <th style="padding: 10px;">Disc</th>
                <th style="padding: 10px;">Status</th>
                <th style="padding: 10px;">Identified</th>
                <th style="padding: 10px;">Time</th>
            </tr>
        </thead>
        <tbody>
            {% for job in jobs %}
            <tr style="border-bottom: 1px solid #222;">
                <td style="padding: 10px;">{{ job.disc_label }}</td>
                <td style="padding: 10px;">
                    <span class="status status-{{ job.status }}">{{ job.status }}</span>
                </td>
                <td style="padding: 10px;">
                    {% if job.identified_title %}
                    {{ job.identified_title }} {% if job.identified_year %}({{ job.identified_year }}){% endif %}
                    {% else %}
                    -
                    {% endif %}
                </td>
                <td style="padding: 10px; color: #888;">{{ job.created_at[:16] }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p style="color: #888;">No jobs yet. Insert a DVD to get started.</p>
    {% endif %}
</div>
{% endblock %}

{% block scripts %}
<script>
document.getElementById('active-toggle').addEventListener('click', async function() {
    const response = await fetch('/api/active-mode', { method: 'POST' });
    const data = await response.json();

    this.textContent = data.active_mode ? 'ON' : 'OFF';
    this.classList.toggle('btn-secondary', !data.active_mode);

    location.reload();
});
</script>
{% endblock %}
```

**Step 2: Commit**

```bash
git add -A
git commit -m "feat: add dashboard template"
```

---

### Task 7.3: Review Queue Template

**Files:**
- Create: `src/dvdtoplex/web/templates/review.html`

**Step 1: Create review template**

```html
{% extends "base.html" %}

{% block title %}Review Queue - DVD-to-Plex{% endblock %}

{% block content %}
<h2 style="margin-bottom: 20px;">Review Queue</h2>

{% if jobs %}
<div class="grid">
    {% for job in jobs %}
    <div class="card">
        <h3>{{ job.disc_label }}</h3>
        <p style="color: #888; margin: 10px 0;">
            Confidence: {{ "%.0f"|format(job.confidence * 100) }}%
        </p>

        <div style="background: #1a1a2e; padding: 15px; border-radius: 4px; margin: 15px 0;">
            <strong>Best Match:</strong>
            <p style="margin-top: 5px;">
                {{ job.identified_title or "Unknown" }}
                {% if job.identified_year %}({{ job.identified_year }}){% endif %}
            </p>
        </div>

        <div style="display: flex; gap: 10px;">
            <button class="btn" onclick="approveJob({{ job.id }})">Approve</button>
            <button class="btn btn-secondary" onclick="editJob({{ job.id }})">Edit</button>
            <button class="btn btn-secondary" onclick="skipJob({{ job.id }})">Skip</button>
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="card">
    <p style="color: #888;">No items need review. Everything is identified!</p>
</div>
{% endif %}
{% endblock %}

{% block scripts %}
<script>
async function approveJob(jobId) {
    await fetch(`/api/jobs/${jobId}/approve`, { method: 'POST' });
    location.reload();
}

function editJob(jobId) {
    const title = prompt('Enter correct title:');
    if (title) {
        fetch(`/api/jobs/${jobId}/identify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        }).then(() => location.reload());
    }
}

async function skipJob(jobId) {
    if (confirm('Skip this disc? It will be removed from the queue.')) {
        await fetch(`/api/jobs/${jobId}/skip`, { method: 'POST' });
        location.reload();
    }
}
</script>
{% endblock %}
```

**Step 2: Commit**

```bash
git add -A
git commit -m "feat: add review queue template"
```

---

### Task 7.4: Collection and Wanted Templates

**Files:**
- Create: `src/dvdtoplex/web/templates/collection.html`
- Create: `src/dvdtoplex/web/templates/wanted.html`

**Step 1: Create collection template**

```html
{% extends "base.html" %}

{% block title %}Collection - DVD-to-Plex{% endblock %}

{% block content %}
<h2 style="margin-bottom: 20px;">Collection</h2>

<div class="card" style="margin-bottom: 20px;">
    <input type="text" id="search" placeholder="Search collection..."
           style="width: 100%; padding: 12px; border: none; border-radius: 4px; background: #1a1a2e; color: #eee; font-size: 1rem;">
</div>

{% if items %}
<div class="grid" id="collection-grid">
    {% for item in items %}
    <div class="card collection-item" data-title="{{ item.title|lower }}">
        <h3>{{ item.title }}</h3>
        {% if item.year %}
        <p style="color: #888;">{{ item.year }}</p>
        {% endif %}
        <span class="status" style="background: #27ae60; margin-top: 10px;">
            {{ item.content_type }}
        </span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="card">
    <p style="color: #888;">Your collection is empty. Rip some DVDs to get started!</p>
</div>
{% endif %}
{% endblock %}

{% block scripts %}
<script>
document.getElementById('search').addEventListener('input', function(e) {
    const query = e.target.value.toLowerCase();
    document.querySelectorAll('.collection-item').forEach(item => {
        const title = item.dataset.title;
        item.style.display = title.includes(query) ? 'block' : 'none';
    });
});
</script>
{% endblock %}
```

**Step 2: Create wanted template**

```html
{% extends "base.html" %}

{% block title %}Wanted - DVD-to-Plex{% endblock %}

{% block content %}
<h2 style="margin-bottom: 20px;">Wanted List</h2>

<div class="card" style="margin-bottom: 20px;">
    <form id="add-wanted" style="display: flex; gap: 10px;">
        <input type="text" name="title" placeholder="Search for a title to add..."
               style="flex: 1; padding: 12px; border: none; border-radius: 4px; background: #1a1a2e; color: #eee; font-size: 1rem;">
        <button type="submit" class="btn">Search</button>
    </form>
</div>

{% if items %}
<div class="grid" id="wanted-grid">
    {% for item in items %}
    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: start;">
            <div>
                <h3>{{ item.title }}</h3>
                {% if item.year %}
                <p style="color: #888;">{{ item.year }}</p>
                {% endif %}
                {% if item.notes %}
                <p style="color: #aaa; font-size: 0.9rem; margin-top: 10px;">{{ item.notes }}</p>
                {% endif %}
            </div>
            <button class="btn btn-secondary" onclick="removeWanted({{ item.id }})" style="padding: 5px 10px; font-size: 0.9rem;">×</button>
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="card">
    <p style="color: #888;">Your wanted list is empty. Search above to add titles you're looking for.</p>
</div>
{% endif %}
{% endblock %}

{% block scripts %}
<script>
document.getElementById('add-wanted').addEventListener('submit', async function(e) {
    e.preventDefault();
    const title = this.title.value;
    if (title) {
        window.location.href = `/wanted/search?q=${encodeURIComponent(title)}`;
    }
});

async function removeWanted(id) {
    if (confirm('Remove from wanted list?')) {
        await fetch(`/api/wanted/${id}`, { method: 'DELETE' });
        location.reload();
    }
}
</script>
{% endblock %}
```

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add collection and wanted templates"
```

---

## Phase 8: Main Entry Point and Service Orchestration

### Task 8.1: Main Application Entry Point

**Files:**
- Create: `src/dvdtoplex/main.py`

**Step 1: Create main entry point**

```python
"""Main entry point for DVD-to-Plex."""

import asyncio
import logging
import signal
from pathlib import Path
from dvdtoplex.config import load_config
from dvdtoplex.database import Database
from dvdtoplex.services.drive_watcher import DriveWatcher
from dvdtoplex.services.rip_queue import RipQueue
from dvdtoplex.services.encode_queue import EncodeQueue
from dvdtoplex.services.identifier import IdentifierService
from dvdtoplex.web import create_app
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Main async entry point."""
    config = load_config()

    # Ensure directories exist
    config.workspace_dir.mkdir(parents=True, exist_ok=True)
    config.ripping_dir.mkdir(exist_ok=True)
    config.encoding_dir.mkdir(exist_ok=True)
    config.staging_dir.mkdir(exist_ok=True)
    config.logs_dir.mkdir(exist_ok=True)
    config.data_dir.mkdir(exist_ok=True)

    # Initialize database
    db = Database(config.db_path)
    await db.initialize()
    logger.info(f"Database initialized at {config.db_path}")

    # Create services
    drive_watcher = DriveWatcher(db)
    rip_queue = RipQueue(db, config)
    encode_queue = EncodeQueue(db, config)
    identifier = IdentifierService(db, config)

    # Create web app
    app = create_app(db, config)

    # Setup shutdown handler
    shutdown_event = asyncio.Event()

    def handle_shutdown(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(sig, lambda s=sig: handle_shutdown(s))

    # Start all services
    tasks = [
        asyncio.create_task(drive_watcher.start()),
        asyncio.create_task(rip_queue.start()),
        asyncio.create_task(encode_queue.start()),
    ]

    # Start web server
    server_config = uvicorn.Config(
        app,
        host=config.web_host,
        port=config.web_port,
        log_level="info",
    )
    server = uvicorn.Server(server_config)
    tasks.append(asyncio.create_task(server.serve()))

    logger.info(f"Web UI available at http://{config.web_host}:{config.web_port}")

    # Wait for shutdown
    await shutdown_event.wait()

    # Stop services
    await drive_watcher.stop()
    await rip_queue.stop()
    await encode_queue.stop()
    await identifier.stop()
    await db.close()

    # Cancel remaining tasks
    for task in tasks:
        task.cancel()

    logger.info("Shutdown complete")


def run():
    """CLI entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
```

**Step 2: Add entry point to pyproject.toml**

Add to `[project.scripts]` section:
```toml
[project.scripts]
dvdtoplex = "dvdtoplex.main:run"
```

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add main entry point and service orchestration"
```

---

## Phase 9: launchd Service Configuration

### Task 9.1: Create launchd Plist Files

**Files:**
- Create: `launchd/com.dvdtoplex.service.plist`
- Create: `scripts/install-service.sh`
- Create: `scripts/uninstall-service.sh`

**Step 1: Create launchd plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.dvdtoplex.service</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/dvdtoplex</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/mediaserver/DVDWorkspace</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/mediaserver/DVDWorkspace/logs/dvdtoplex.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/mediaserver/DVDWorkspace/logs/dvdtoplex.err</string>
</dict>
</plist>
```

**Step 2: Create install script**

```bash
#!/bin/bash
set -e

PLIST_NAME="com.dvdtoplex.service"
PLIST_SRC="$(dirname "$0")/../launchd/${PLIST_NAME}.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "Installing DVD-to-Plex service..."

# Copy plist
cp "$PLIST_SRC" "$PLIST_DEST"

# Update paths in plist for current user
sed -i '' "s|/Users/mediaserver|$HOME|g" "$PLIST_DEST"

# Load the service
launchctl load "$PLIST_DEST"

echo "Service installed and started."
echo "View logs: tail -f ~/DVDWorkspace/logs/dvdtoplex.log"
echo "Web UI: http://localhost:8080"
```

**Step 3: Create uninstall script**

```bash
#!/bin/bash
set -e

PLIST_NAME="com.dvdtoplex.service"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "Uninstalling DVD-to-Plex service..."

# Unload the service
launchctl unload "$PLIST_PATH" 2>/dev/null || true

# Remove plist
rm -f "$PLIST_PATH"

echo "Service uninstalled."
```

**Step 4: Make scripts executable**

Run:
```bash
mkdir -p launchd scripts
chmod +x scripts/install-service.sh scripts/uninstall-service.sh
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add launchd service configuration"
```

---

## Phase 10: File Mover Service

### Task 10.1: Plex File Mover

**Files:**
- Create: `src/dvdtoplex/services/file_mover.py`
- Create: `tests/test_file_mover.py`

**Step 1: Write failing test**

```python
"""Tests for file mover service."""

import pytest
from pathlib import Path
from dvdtoplex.services.file_mover import format_movie_filename, format_tv_filename


def test_format_movie_filename():
    """Test movie filename formatting."""
    result = format_movie_filename("The Matrix", 1999)
    assert result == "The Matrix (1999).mkv"


def test_format_movie_filename_special_chars():
    """Test filename with special characters."""
    result = format_movie_filename("Se7en", 1995)
    assert result == "Se7en (1995).mkv"


def test_format_tv_filename():
    """Test TV episode filename formatting."""
    result = format_tv_filename("Breaking Bad", 4, 1, "Box Cutter")
    assert result == "Breaking Bad - S04E01 - Box Cutter.mkv"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_file_mover.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
"""File mover service - moves completed encodes to Plex library."""

import asyncio
import logging
import shutil
import re
from pathlib import Path
from typing import Optional
from dvdtoplex.database import Database, JobStatus, ContentType
from dvdtoplex.config import Config

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Remove characters not allowed in filenames."""
    # Remove or replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Remove leading/trailing whitespace and dots
    name = name.strip('. ')
    return name


def format_movie_filename(title: str, year: int) -> str:
    """Format movie filename for Plex."""
    title = sanitize_filename(title)
    return f"{title} ({year}).mkv"


def format_tv_filename(show: str, season: int, episode: int, title: str) -> str:
    """Format TV episode filename for Plex."""
    show = sanitize_filename(show)
    title = sanitize_filename(title)
    return f"{show} - S{season:02d}E{episode:02d} - {title}.mkv"


class FileMover:
    """Moves completed encodes to Plex library."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config
        self._running = False

    async def start(self) -> None:
        """Start the file mover service."""
        self._running = True
        logger.info("File mover started")

        while self._running:
            await self._process_pending_moves()
            await asyncio.sleep(5.0)

    async def stop(self) -> None:
        """Stop the file mover service."""
        self._running = False
        logger.info("File mover stopped")

    async def _process_pending_moves(self) -> None:
        """Process jobs ready to move to Plex."""
        cursor = await self.db._conn.execute(
            "SELECT * FROM jobs WHERE status = ?",
            (JobStatus.MOVING.value,)
        )
        rows = await cursor.fetchall()

        for row in rows:
            job = dict(row)
            await self._move_job(job)

    async def _move_job(self, job: dict) -> None:
        """Move a single job to Plex library."""
        job_id = job["id"]
        encode_path = Path(job["encode_path"])
        content_type = ContentType(job["content_type"])
        title = job["identified_title"]
        year = job["identified_year"]

        logger.info(f"Moving job {job_id}: {title}")

        try:
            if not encode_path.exists():
                raise Exception(f"Encode file not found: {encode_path}")

            # Check if Plex drive is available
            if content_type == ContentType.MOVIE:
                dest_dir = self.config.plex_movies_dir
            else:
                dest_dir = self.config.plex_tv_dir

            if not dest_dir.exists():
                logger.warning(f"Plex directory not available: {dest_dir}")
                return  # Will retry later

            # Format filename and destination
            if content_type == ContentType.MOVIE:
                filename = format_movie_filename(title, year)
                # Movies go in a folder
                movie_dir = dest_dir / f"{title} ({year})"
                movie_dir.mkdir(exist_ok=True)
                final_path = movie_dir / filename
            else:
                # TV handling would go here
                logger.warning("TV show moving not yet implemented")
                return

            # Move the file
            logger.info(f"Moving to: {final_path}")
            shutil.move(str(encode_path), str(final_path))

            # Update job
            await self.db._conn.execute(
                "UPDATE jobs SET final_path = ? WHERE id = ?",
                (str(final_path), job_id)
            )
            await self.db.update_job_status(job_id, JobStatus.COMPLETE)

            # Add to collection
            await self.db._conn.execute("""
                INSERT INTO collection (content_type, title, year, tmdb_id, file_path)
                VALUES (?, ?, ?, ?, ?)
            """, (content_type.value, title, year, job["tmdb_id"], str(final_path)))
            await self.db._conn.commit()

            # Clean up job directories
            encode_dir = encode_path.parent
            rip_path = Path(job["rip_path"]) if job["rip_path"] else None

            if encode_dir.exists() and encode_dir != self.config.encoding_dir:
                shutil.rmtree(encode_dir)
            if rip_path and rip_path.parent.exists():
                shutil.rmtree(rip_path.parent)

            logger.info(f"Job {job_id} complete: {title} ({year})")

        except Exception as e:
            logger.error(f"Failed to move job {job_id}: {e}")
            await self.db._conn.execute(
                "UPDATE jobs SET error_message = ? WHERE id = ?",
                (str(e), job_id)
            )
            await self.db.update_job_status(job_id, JobStatus.FAILED)
```

**Step 4: Run tests**

Run: `pytest tests/test_file_mover.py -v`
Expected: PASS

**Step 5: Update main.py to include file mover**

Add import and create service, add to tasks.

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: add file mover service for Plex library"
```

---

## Phase 11: Integration Testing

### Task 11.1: End-to-End Test Setup

**Files:**
- Create: `tests/integration/test_pipeline.py`

**Step 1: Create integration test**

```python
"""Integration tests for the full pipeline."""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from dvdtoplex.database import Database, JobStatus
from dvdtoplex.config import Config


@pytest.fixture
async def test_config(tmp_path):
    """Create test configuration."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    return Config(
        pushover_user_key="test",
        pushover_api_token="test",
        tmdb_api_token="test",
        workspace_dir=workspace,
        plex_movies_dir=tmp_path / "Movies",
        plex_tv_dir=tmp_path / "TV",
        web_host="127.0.0.1",
        web_port=8080,
    )


@pytest.fixture
async def test_db(test_config):
    """Create test database."""
    db = Database(test_config.db_path)
    await db.initialize()
    yield db
    await db.close()


async def test_job_state_transitions(test_db):
    """Test that jobs transition through states correctly."""
    # Create a job
    job_id = await test_db.create_rip_job(
        drive_id="1",
        disc_label="THE_MATRIX",
    )

    job = await test_db.get_job(job_id)
    assert job["status"] == JobStatus.PENDING.value

    # Simulate state transitions
    for status in [JobStatus.RIPPING, JobStatus.RIPPED, JobStatus.ENCODING,
                   JobStatus.ENCODED, JobStatus.IDENTIFYING, JobStatus.MOVING,
                   JobStatus.COMPLETE]:
        await test_db.update_job_status(job_id, status)
        job = await test_db.get_job(job_id)
        assert job["status"] == status.value
```

**Step 2: Run integration tests**

Run: `pytest tests/integration/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add integration test infrastructure"
```

---

## Final Checklist

After all phases complete:

1. [ ] Run full test suite: `pytest --cov=dvdtoplex`
2. [ ] Create `.env` from `.env.example` with actual credentials
3. [ ] Install package: `pip install -e .`
4. [ ] Test manually with a real DVD
5. [ ] Install launchd service: `./scripts/install-service.sh`
6. [ ] Verify web UI at http://localhost:8080
7. [ ] Test Pushover notifications

---

## Notes for Implementer

- Each task follows TDD: write test, verify fail, implement, verify pass, commit
- The identifier service is placeholder - Claude Code SDK integration would be Phase 12
- TV season handling is stubbed - implement after movies work end-to-end
- Screenshot extraction (ffmpeg) not yet implemented - add to identifier service
- Subtitle OCR (Tesseract) not yet implemented - add to encode queue
