# Google Sheets Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Sync owned movies (from Plex directory) and wishlist (from database) to a Google Sheet with two structured tables.

**Architecture:** New `google_sheets.py` module handles Sheets API via gspread with service account auth. New `SheetsSyncService` runs daily, scans Plex directories, reads wanted items from SQLite, and pushes both to Google Sheets as structured tables.

**Tech Stack:** gspread (Google Sheets API wrapper), existing BaseService pattern, pytest-asyncio for tests.

---

## Task 1: Add gspread Dependency

**Files:**
- Modify: `pyproject.toml:10-18`

**Step 1: Add gspread to dependencies**

Edit `pyproject.toml` dependencies list to add gspread:

```toml
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "httpx>=0.25.0",
    "python-dotenv>=1.0.0",
    "aiosqlite>=0.19.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.6",
    "gspread>=6.0.0",
]
```

**Step 2: Install dependencies**

Run: `pip install -e .`
Expected: Successfully installed gspread and dependencies

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add gspread dependency for Google Sheets sync"
```

---

## Task 2: Add Configuration for Google Sheets

**Files:**
- Modify: `src/dvdtoplex/config.py:17-34` (Config dataclass)
- Modify: `src/dvdtoplex/config.py:65-93` (load_config function)
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_google_sheets_config_from_env(monkeypatch, tmp_path):
    """Test Google Sheets config loads from environment."""
    creds_file = tmp_path / "creds.json"
    creds_file.write_text("{}")

    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_FILE", str(creds_file))
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "test_spreadsheet_id")
    monkeypatch.setenv("SHEETS_SYNC_INTERVAL", "12")

    from dvdtoplex.config import load_config
    config = load_config()

    assert config.google_sheets_credentials_file == creds_file
    assert config.google_sheets_spreadsheet_id == "test_spreadsheet_id"
    assert config.sheets_sync_interval == 12


def test_google_sheets_config_defaults(monkeypatch):
    """Test Google Sheets config has sensible defaults."""
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SHEETS_SYNC_INTERVAL", raising=False)

    from dvdtoplex.config import load_config
    config = load_config()

    assert config.google_sheets_credentials_file is None
    assert config.google_sheets_spreadsheet_id is None
    assert config.sheets_sync_interval == 24
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_google_sheets_config_from_env -v`
Expected: FAIL with AttributeError (no google_sheets_credentials_file)

**Step 3: Add config fields to Config dataclass**

In `src/dvdtoplex/config.py`, add to the Config dataclass after line 34:

```python
    google_sheets_credentials_file: Path | None = None
    google_sheets_spreadsheet_id: str | None = None
    sheets_sync_interval: int = 24  # hours
```

**Step 4: Update load_config function**

In `src/dvdtoplex/config.py`, update the load_config return statement to include:

```python
    # Google Sheets config
    sheets_creds = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE")
    sheets_creds_path = Path(sheets_creds).expanduser() if sheets_creds else None

    return Config(
        # ... existing fields ...
        google_sheets_credentials_file=sheets_creds_path,
        google_sheets_spreadsheet_id=os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID"),
        sheets_sync_interval=int(os.getenv("SHEETS_SYNC_INTERVAL", "24")),
    )
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/dvdtoplex/config.py tests/test_config.py
git commit -m "feat: add Google Sheets configuration options"
```

---

## Task 3: Create Plex Directory Scanner

**Files:**
- Create: `src/dvdtoplex/plex_scanner.py`
- Test: `tests/test_plex_scanner.py`

**Step 1: Write the failing test**

Create `tests/test_plex_scanner.py`:

```python
"""Tests for Plex directory scanner."""

import pytest
from pathlib import Path


def test_scan_movies_extracts_title_and_year(tmp_path):
    """Test scanner extracts title and year from folder names."""
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    (movies_dir / "The Matrix (1999)").mkdir()
    (movies_dir / "Inception (2010)").mkdir()

    from dvdtoplex.plex_scanner import scan_plex_movies

    movies = scan_plex_movies(movies_dir)

    assert len(movies) == 2
    assert {"title": "The Matrix", "year": 1999} in movies
    assert {"title": "Inception", "year": 2010} in movies


def test_scan_movies_handles_no_year(tmp_path):
    """Test scanner handles folders without year."""
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    (movies_dir / "Some Movie Without Year").mkdir()

    from dvdtoplex.plex_scanner import scan_plex_movies

    movies = scan_plex_movies(movies_dir)

    assert len(movies) == 1
    assert movies[0]["title"] == "Some Movie Without Year"
    assert movies[0]["year"] is None


def test_scan_movies_skips_hidden_folders(tmp_path):
    """Test scanner skips hidden folders."""
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    (movies_dir / ".hidden").mkdir()
    (movies_dir / "Visible Movie (2020)").mkdir()

    from dvdtoplex.plex_scanner import scan_plex_movies

    movies = scan_plex_movies(movies_dir)

    assert len(movies) == 1
    assert movies[0]["title"] == "Visible Movie"


def test_scan_movies_skips_files(tmp_path):
    """Test scanner only processes directories."""
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    (movies_dir / "movie.mkv").touch()
    (movies_dir / "Real Movie (2020)").mkdir()

    from dvdtoplex.plex_scanner import scan_plex_movies

    movies = scan_plex_movies(movies_dir)

    assert len(movies) == 1


def test_scan_movies_empty_directory(tmp_path):
    """Test scanner handles empty directory."""
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()

    from dvdtoplex.plex_scanner import scan_plex_movies

    movies = scan_plex_movies(movies_dir)

    assert movies == []


def test_scan_movies_nonexistent_directory(tmp_path):
    """Test scanner handles nonexistent directory."""
    movies_dir = tmp_path / "DoesNotExist"

    from dvdtoplex.plex_scanner import scan_plex_movies

    movies = scan_plex_movies(movies_dir)

    assert movies == []


def test_scan_movies_sorted_by_title(tmp_path):
    """Test scanner returns movies sorted by title."""
    movies_dir = tmp_path / "Movies"
    movies_dir.mkdir()
    (movies_dir / "Zebra (2020)").mkdir()
    (movies_dir / "Alpha (2019)").mkdir()
    (movies_dir / "Beta (2018)").mkdir()

    from dvdtoplex.plex_scanner import scan_plex_movies

    movies = scan_plex_movies(movies_dir)

    titles = [m["title"] for m in movies]
    assert titles == ["Alpha", "Beta", "Zebra"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_plex_scanner.py::test_scan_movies_extracts_title_and_year -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement plex_scanner module**

Create `src/dvdtoplex/plex_scanner.py`:

```python
"""Plex directory scanner for extracting movie information."""

import re
from pathlib import Path


def scan_plex_movies(movies_dir: Path) -> list[dict[str, str | int | None]]:
    """Scan Plex movies directory and extract title/year from folder names.

    Args:
        movies_dir: Path to the Plex Movies directory.

    Returns:
        List of dicts with 'title' and 'year' keys, sorted by title.
    """
    if not movies_dir.exists():
        return []

    movies = []
    pattern = re.compile(r"^(.+?)\s*\((\d{4})\)$")

    for item in movies_dir.iterdir():
        # Skip files and hidden folders
        if not item.is_dir() or item.name.startswith("."):
            continue

        match = pattern.match(item.name)
        if match:
            title = match.group(1).strip()
            year = int(match.group(2))
        else:
            title = item.name
            year = None

        movies.append({"title": title, "year": year})

    return sorted(movies, key=lambda m: m["title"])
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plex_scanner.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/dvdtoplex/plex_scanner.py tests/test_plex_scanner.py
git commit -m "feat: add Plex directory scanner"
```

---

## Task 4: Create Google Sheets Client

**Files:**
- Create: `src/dvdtoplex/google_sheets.py`
- Test: `tests/test_google_sheets.py`

**Step 1: Write the failing test**

Create `tests/test_google_sheets.py`:

```python
"""Tests for Google Sheets client."""

import pytest
from unittest.mock import Mock, patch, MagicMock


def test_sheets_client_init_with_credentials(tmp_path):
    """Test client initializes with credentials file."""
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"type": "service_account"}')

    with patch("dvdtoplex.google_sheets.gspread") as mock_gspread:
        mock_gspread.service_account.return_value = Mock()

        from dvdtoplex.google_sheets import GoogleSheetsClient

        client = GoogleSheetsClient(creds_file, "spreadsheet_id")

        mock_gspread.service_account.assert_called_once_with(filename=str(creds_file))


def test_sheets_client_update_owned_movies():
    """Test updating owned movies sheet."""
    with patch("dvdtoplex.google_sheets.gspread") as mock_gspread:
        mock_gc = Mock()
        mock_spreadsheet = Mock()
        mock_worksheet = Mock()

        mock_gspread.service_account.return_value = mock_gc
        mock_gc.open_by_key.return_value = mock_spreadsheet
        mock_spreadsheet.worksheet.return_value = mock_worksheet

        from dvdtoplex.google_sheets import GoogleSheetsClient

        client = GoogleSheetsClient(None, "spreadsheet_id")
        client._gc = mock_gc

        movies = [
            {"title": "The Matrix", "year": 1999},
            {"title": "Inception", "year": 2010},
        ]

        client.update_owned_movies(movies)

        mock_spreadsheet.worksheet.assert_called_with("Owned")
        # Verify clear and update were called
        assert mock_worksheet.clear.called
        assert mock_worksheet.update.called


def test_sheets_client_update_wishlist_with_posters():
    """Test updating wishlist with poster images."""
    with patch("dvdtoplex.google_sheets.gspread") as mock_gspread:
        mock_gc = Mock()
        mock_spreadsheet = Mock()
        mock_worksheet = Mock()

        mock_gspread.service_account.return_value = mock_gc
        mock_gc.open_by_key.return_value = mock_spreadsheet
        mock_spreadsheet.worksheet.return_value = mock_worksheet

        from dvdtoplex.google_sheets import GoogleSheetsClient

        client = GoogleSheetsClient(None, "spreadsheet_id")
        client._gc = mock_gc

        items = [
            {"title": "Dune", "year": 2021, "poster_path": "/abc123.jpg"},
        ]

        client.update_wishlist(items)

        mock_spreadsheet.worksheet.assert_called_with("Wishlist")
        # Verify the IMAGE formula is included
        call_args = mock_worksheet.update.call_args
        data = call_args[0][0]  # First positional argument
        # Row 1 is header, Row 2 is data
        assert any("=IMAGE(" in str(row) for row in data)


def test_format_poster_url():
    """Test poster URL formatting."""
    from dvdtoplex.google_sheets import format_poster_url

    url = format_poster_url("/abc123.jpg")
    assert url == "https://image.tmdb.org/t/p/w200/abc123.jpg"


def test_format_poster_url_none():
    """Test poster URL formatting with None."""
    from dvdtoplex.google_sheets import format_poster_url

    url = format_poster_url(None)
    assert url == ""


def test_format_image_formula():
    """Test IMAGE formula formatting."""
    from dvdtoplex.google_sheets import format_image_formula

    formula = format_image_formula("https://example.com/image.jpg")
    assert formula == '=IMAGE("https://example.com/image.jpg")'


def test_format_image_formula_empty():
    """Test IMAGE formula with empty URL."""
    from dvdtoplex.google_sheets import format_image_formula

    formula = format_image_formula("")
    assert formula == ""
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_google_sheets.py::test_format_poster_url -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement google_sheets module**

Create `src/dvdtoplex/google_sheets.py`:

```python
"""Google Sheets client for syncing movie data."""

import logging
from pathlib import Path
from typing import Any

import gspread

logger = logging.getLogger(__name__)

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w200"


def format_poster_url(poster_path: str | None) -> str:
    """Format a TMDb poster path into a full URL.

    Args:
        poster_path: TMDb poster path (e.g., "/abc123.jpg") or None.

    Returns:
        Full poster URL or empty string if no path.
    """
    if not poster_path:
        return ""
    return f"{TMDB_IMAGE_BASE}{poster_path}"


def format_image_formula(url: str) -> str:
    """Format a URL as a Google Sheets IMAGE formula.

    Args:
        url: Image URL.

    Returns:
        Google Sheets IMAGE formula or empty string if no URL.
    """
    if not url:
        return ""
    return f'=IMAGE("{url}")'


class GoogleSheetsClient:
    """Client for interacting with Google Sheets."""

    def __init__(
        self,
        credentials_file: Path | None,
        spreadsheet_id: str,
    ) -> None:
        """Initialize the Google Sheets client.

        Args:
            credentials_file: Path to service account JSON file.
            spreadsheet_id: Google Sheets spreadsheet ID.
        """
        self._credentials_file = credentials_file
        self._spreadsheet_id = spreadsheet_id
        self._gc: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None

    def connect(self) -> None:
        """Connect to Google Sheets API."""
        if self._credentials_file:
            self._gc = gspread.service_account(filename=str(self._credentials_file))
        else:
            # For testing - client must be set manually
            return
        self._spreadsheet = self._gc.open_by_key(self._spreadsheet_id)
        logger.info("Connected to Google Sheets: %s", self._spreadsheet.title)

    def _get_spreadsheet(self) -> gspread.Spreadsheet:
        """Get the spreadsheet, connecting if needed."""
        if self._spreadsheet is None:
            if self._gc is None:
                raise RuntimeError("Not connected to Google Sheets")
            self._spreadsheet = self._gc.open_by_key(self._spreadsheet_id)
        return self._spreadsheet

    def update_owned_movies(self, movies: list[dict[str, Any]]) -> None:
        """Update the Owned sheet with movie data.

        Args:
            movies: List of dicts with 'title' and 'year' keys.
        """
        spreadsheet = self._get_spreadsheet()
        worksheet = spreadsheet.worksheet("Owned")

        # Clear existing data
        worksheet.clear()

        # Prepare data with header
        data = [["Title", "Year"]]
        for movie in movies:
            data.append([movie["title"], movie["year"] or ""])

        # Write all data
        worksheet.update(data, value_input_option="USER_ENTERED")
        logger.info("Updated Owned sheet with %d movies", len(movies))

    def update_wishlist(self, items: list[dict[str, Any]]) -> None:
        """Update the Wishlist sheet with wanted items.

        Args:
            items: List of dicts with 'title', 'year', and 'poster_path' keys.
        """
        spreadsheet = self._get_spreadsheet()
        worksheet = spreadsheet.worksheet("Wishlist")

        # Clear existing data
        worksheet.clear()

        # Prepare data with header
        data = [["Title", "Year", "Poster URL", "Poster"]]
        for item in items:
            poster_url = format_poster_url(item.get("poster_path"))
            image_formula = format_image_formula(poster_url)
            data.append([
                item["title"],
                item.get("year") or "",
                poster_url,
                image_formula,
            ])

        # Write all data
        worksheet.update(data, value_input_option="USER_ENTERED")
        logger.info("Updated Wishlist sheet with %d items", len(items))
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_google_sheets.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/dvdtoplex/google_sheets.py tests/test_google_sheets.py
git commit -m "feat: add Google Sheets client"
```

---

## Task 5: Create Sheets Sync Service

**Files:**
- Create: `src/dvdtoplex/services/sheets_sync.py`
- Test: `tests/test_sheets_sync.py`

**Step 1: Write the failing test**

Create `tests/test_sheets_sync.py`:

```python
"""Tests for Google Sheets sync service."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path


@pytest.fixture
def mock_config(tmp_path):
    """Create mock config with Google Sheets settings."""
    config = Mock()
    config.google_sheets_credentials_file = tmp_path / "creds.json"
    config.google_sheets_spreadsheet_id = "test_spreadsheet_id"
    config.sheets_sync_interval = 24
    config.plex_movies_dir = tmp_path / "Movies"
    config.plex_movies_dir.mkdir()
    return config


@pytest.fixture
def mock_database():
    """Create mock database."""
    db = AsyncMock()
    db.get_wanted = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_sheets_sync_service_disabled_without_config():
    """Test service is disabled when credentials not configured."""
    config = Mock()
    config.google_sheets_credentials_file = None
    config.google_sheets_spreadsheet_id = None

    from dvdtoplex.services.sheets_sync import SheetsSyncService

    service = SheetsSyncService(config, Mock())

    assert not service.is_enabled


@pytest.mark.asyncio
async def test_sheets_sync_service_enabled_with_config(mock_config, mock_database):
    """Test service is enabled when credentials configured."""
    from dvdtoplex.services.sheets_sync import SheetsSyncService

    service = SheetsSyncService(mock_config, mock_database)

    assert service.is_enabled


@pytest.mark.asyncio
async def test_sheets_sync_performs_sync(mock_config, mock_database, tmp_path):
    """Test sync collects data and updates sheets."""
    # Create test movie folder
    (mock_config.plex_movies_dir / "The Matrix (1999)").mkdir()

    # Mock wanted items
    mock_database.get_wanted.return_value = [
        Mock(title="Dune", year=2021, poster_path="/abc.jpg"),
    ]

    with patch("dvdtoplex.services.sheets_sync.GoogleSheetsClient") as MockClient:
        mock_client = Mock()
        MockClient.return_value = mock_client

        from dvdtoplex.services.sheets_sync import SheetsSyncService

        service = SheetsSyncService(mock_config, mock_database)
        await service.sync_now()

        # Verify client was created and used
        mock_client.connect.assert_called_once()
        mock_client.update_owned_movies.assert_called_once()
        mock_client.update_wishlist.assert_called_once()

        # Verify owned movies data
        owned_call = mock_client.update_owned_movies.call_args[0][0]
        assert len(owned_call) == 1
        assert owned_call[0]["title"] == "The Matrix"

        # Verify wishlist data
        wishlist_call = mock_client.update_wishlist.call_args[0][0]
        assert len(wishlist_call) == 1
        assert wishlist_call[0]["title"] == "Dune"


@pytest.mark.asyncio
async def test_sheets_sync_handles_missing_poster_path(mock_config, mock_database):
    """Test sync handles wanted items without poster_path."""
    mock_database.get_wanted.return_value = [
        Mock(title="Old Movie", year=1990, poster_path=None),
    ]

    with patch("dvdtoplex.services.sheets_sync.GoogleSheetsClient") as MockClient:
        mock_client = Mock()
        MockClient.return_value = mock_client

        from dvdtoplex.services.sheets_sync import SheetsSyncService

        service = SheetsSyncService(mock_config, mock_database)
        await service.sync_now()

        wishlist_call = mock_client.update_wishlist.call_args[0][0]
        assert wishlist_call[0]["poster_path"] is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_sheets_sync.py::test_sheets_sync_service_disabled_without_config -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement sheets_sync service**

Create `src/dvdtoplex/services/sheets_sync.py`:

```python
"""Google Sheets sync service."""

import asyncio
import logging
from typing import TYPE_CHECKING

from dvdtoplex.google_sheets import GoogleSheetsClient
from dvdtoplex.plex_scanner import scan_plex_movies
from dvdtoplex.services.base import BaseService

if TYPE_CHECKING:
    from dvdtoplex.config import Config
    from dvdtoplex.database import Database

logger = logging.getLogger(__name__)


class SheetsSyncService(BaseService):
    """Service that syncs movie data to Google Sheets on a schedule."""

    def __init__(self, config: "Config", database: "Database") -> None:
        """Initialize the sync service.

        Args:
            config: Application configuration.
            database: Database instance.
        """
        super().__init__("sheets_sync")
        self._config = config
        self._database = database
        self._sync_interval_hours = config.sheets_sync_interval

    @property
    def is_enabled(self) -> bool:
        """Check if the service is enabled (credentials configured)."""
        return (
            self._config.google_sheets_credentials_file is not None
            and self._config.google_sheets_spreadsheet_id is not None
        )

    async def _run(self) -> None:
        """Main service loop - sync periodically."""
        if not self.is_enabled:
            self._logger.info("Google Sheets sync disabled (no credentials configured)")
            return

        # Initial sync on startup
        await self.sync_now()

        # Then sync on schedule
        while not self.should_stop():
            # Wait for next sync interval
            stopped = await self.wait_for_stop(
                timeout=self._sync_interval_hours * 3600
            )
            if stopped:
                break

            await self.sync_now()

    async def sync_now(self) -> None:
        """Perform a sync immediately."""
        if not self.is_enabled:
            self._logger.warning("Cannot sync - Google Sheets not configured")
            return

        self._logger.info("Starting Google Sheets sync...")

        try:
            # Create client
            client = GoogleSheetsClient(
                self._config.google_sheets_credentials_file,
                self._config.google_sheets_spreadsheet_id,
            )
            client.connect()

            # Scan Plex movies
            movies = scan_plex_movies(self._config.plex_movies_dir)
            self._logger.info("Found %d movies in Plex directory", len(movies))

            # Get wanted items from database
            wanted_items = await self._database.get_wanted()
            wishlist = [
                {
                    "title": item.title,
                    "year": item.year,
                    "poster_path": getattr(item, "poster_path", None),
                }
                for item in wanted_items
            ]
            self._logger.info("Found %d items in wishlist", len(wishlist))

            # Update sheets
            client.update_owned_movies(movies)
            client.update_wishlist(wishlist)

            self._logger.info("Google Sheets sync completed successfully")

        except Exception as e:
            self._logger.error("Google Sheets sync failed: %s", e)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/dvdtoplex/services/sheets_sync.py tests/test_sheets_sync.py
git commit -m "feat: add Google Sheets sync service"
```

---

## Task 6: Add poster_path to WantedItem

**Files:**
- Modify: `src/dvdtoplex/database.py:116-126` (WantedItem dataclass)
- Modify: `src/dvdtoplex/database.py:245-253` (wanted table schema)
- Modify: `src/dvdtoplex/database.py:865-897` (add_to_wanted method)
- Modify: `src/dvdtoplex/database.py:899-920` (get_wanted method)
- Test: `tests/test_database.py`

**Step 1: Write the failing test**

Add to `tests/test_database.py`:

```python
@pytest.mark.asyncio
async def test_wanted_item_stores_poster_path(tmp_path):
    """Test wanted items can store poster_path."""
    from dvdtoplex.database import Database, ContentType

    db = Database(tmp_path / "test.db")
    await db.connect()

    try:
        item_id = await db.add_to_wanted(
            title="Dune",
            year=2021,
            content_type=ContentType.MOVIE,
            tmdb_id=438631,
            poster_path="/abc123.jpg",
        )

        item = await db.get_wanted_item(item_id)

        assert item is not None
        assert item.poster_path == "/abc123.jpg"
    finally:
        await db.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py::test_wanted_item_stores_poster_path -v`
Expected: FAIL (TypeError: unexpected keyword argument 'poster_path')

**Step 3: Add poster_path to WantedItem dataclass**

In `src/dvdtoplex/database.py`, update WantedItem (around line 116):

```python
@dataclass
class WantedItem:
    """Represents an item in the user's wanted list."""

    id: int
    title: str
    year: int | None
    content_type: ContentType
    tmdb_id: int | None
    poster_path: str | None
    notes: str | None
    added_at: datetime
```

**Step 4: Update wanted table schema**

In `src/dvdtoplex/database.py`, update the CREATE TABLE wanted statement:

```sql
CREATE TABLE IF NOT EXISTS wanted (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    year INTEGER,
    content_type TEXT NOT NULL DEFAULT 'movie',
    tmdb_id INTEGER,
    poster_path TEXT,
    notes TEXT,
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Step 5: Add migration for poster_path column**

In `src/dvdtoplex/database.py`, add to `_run_migrations` method:

```python
# Check if poster_path column exists in wanted table
cursor = await self.connection.execute("PRAGMA table_info(wanted)")
columns = await cursor.fetchall()
wanted_column_names = {col["name"] for col in columns}

if "poster_path" not in wanted_column_names:
    await self.connection.execute(
        "ALTER TABLE wanted ADD COLUMN poster_path TEXT"
    )
    await self.connection.commit()
```

**Step 6: Update add_to_wanted method**

In `src/dvdtoplex/database.py`, update add_to_wanted signature and body:

```python
async def add_to_wanted(
    self,
    title: str,
    year: int | None = None,
    content_type: ContentType | str = ContentType.MOVIE,
    tmdb_id: int | None = None,
    poster_path: str | None = None,
    notes: str | None = None,
) -> int:
    """Add an item to the wanted list."""
    content_type_value = (
        content_type.value if isinstance(content_type, ContentType) else content_type
    )
    cursor = await self.connection.execute(
        """
        INSERT INTO wanted (title, year, content_type, tmdb_id, poster_path, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (title, year, content_type_value, tmdb_id, poster_path, notes),
    )
    await self.connection.commit()
    return cursor.lastrowid or 0
```

**Step 7: Update get_wanted and get_wanted_item methods**

Update to include poster_path in the WantedItem construction:

```python
async def get_wanted(self) -> list[WantedItem]:
    """Get all items in the wanted list."""
    cursor = await self.connection.execute(
        "SELECT * FROM wanted ORDER BY added_at DESC, id DESC"
    )
    rows = await cursor.fetchall()
    return [
        WantedItem(
            id=row["id"],
            title=row["title"],
            year=row["year"],
            content_type=ContentType(row["content_type"]),
            tmdb_id=row["tmdb_id"],
            poster_path=row["poster_path"],
            notes=row["notes"],
            added_at=datetime.fromisoformat(row["added_at"]),
        )
        for row in rows
    ]

async def get_wanted_item(self, item_id: int) -> WantedItem | None:
    """Get a wanted item by ID."""
    cursor = await self.connection.execute(
        "SELECT * FROM wanted WHERE id = ?", (item_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return WantedItem(
        id=row["id"],
        title=row["title"],
        year=row["year"],
        content_type=ContentType(row["content_type"]),
        tmdb_id=row["tmdb_id"],
        poster_path=row["poster_path"],
        notes=row["notes"],
        added_at=datetime.fromisoformat(row["added_at"]),
    )
```

**Step 8: Run tests to verify they pass**

Run: `pytest tests/test_database.py -v`
Expected: All PASS

**Step 9: Commit**

```bash
git add src/dvdtoplex/database.py tests/test_database.py
git commit -m "feat: add poster_path to wanted items"
```

---

## Task 7: Update Web API to Store poster_path for Wanted Items

**Files:**
- Modify: `src/dvdtoplex/web/app.py` (add_wanted endpoint)
- Test: `tests/test_web_wanted.py`

**Step 1: Write the failing test**

Add to `tests/test_web_wanted.py`:

```python
@pytest.mark.asyncio
async def test_add_wanted_stores_poster_path(test_client, mock_database):
    """Test adding wanted item stores poster_path."""
    response = test_client.post(
        "/api/wanted",
        json={
            "title": "Dune",
            "year": 2021,
            "content_type": "movie",
            "tmdb_id": 438631,
            "poster_path": "/abc123.jpg",
        },
    )

    assert response.status_code == 200

    # Verify poster_path was passed to database
    call_kwargs = mock_database.add_to_wanted.call_args.kwargs
    assert call_kwargs.get("poster_path") == "/abc123.jpg"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_wanted.py::test_add_wanted_stores_poster_path -v`
Expected: FAIL (poster_path not in call_kwargs)

**Step 3: Update WantedRequest model**

In `src/dvdtoplex/web/app.py`, update the WantedRequest model:

```python
class WantedRequest(BaseModel):
    """Request body for adding to wanted list."""

    title: str
    year: int | None = None
    content_type: str = "movie"
    tmdb_id: int | None = None
    poster_path: str | None = None
    notes: str | None = None
```

**Step 4: Update add_wanted endpoint**

In `src/dvdtoplex/web/app.py`, update the add_wanted endpoint to pass poster_path:

```python
await database.add_to_wanted(
    title=body.title,
    year=body.year,
    content_type=body.content_type,
    tmdb_id=body.tmdb_id,
    poster_path=body.poster_path,
    notes=body.notes,
)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_web_wanted.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/dvdtoplex/web/app.py tests/test_web_wanted.py
git commit -m "feat: store poster_path when adding wanted items"
```

---

## Task 8: Integrate Sheets Sync Service into Main Application

**Files:**
- Modify: `src/dvdtoplex/main.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

Add to `tests/test_main.py`:

```python
@pytest.mark.asyncio
async def test_application_includes_sheets_sync_service(tmp_path, monkeypatch):
    """Test Application includes SheetsSyncService when configured."""
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_FILE", str(tmp_path / "creds.json"))
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "test_id")

    from dvdtoplex.config import load_config
    from dvdtoplex.main import Application
    from dvdtoplex.services.sheets_sync import SheetsSyncService

    config = load_config()
    config.workspace_dir = tmp_path / "workspace"
    config.workspace_dir.mkdir()

    app = Application(config)

    # Check that SheetsSyncService is in the services list
    service_types = [type(s).__name__ for s in app.services]
    assert "SheetsSyncService" in service_types
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::test_application_includes_sheets_sync_service -v`
Expected: FAIL (SheetsSyncService not in service_types)

**Step 3: Import and add SheetsSyncService to Application**

In `src/dvdtoplex/main.py`, add the import:

```python
from dvdtoplex.services.sheets_sync import SheetsSyncService
```

Then in the Application `__init__` method, add the service:

```python
# Create services (but don't start yet)
self.drive_watcher = DriveWatcher(self.config, self.database, self.config.drive_ids)
rip_queue = RipQueue(self.config, self.database, self.config.drive_ids)
encode_queue = EncodeQueue(self.config, self.database)
identifier = IdentifierService(self.database, self.config)
file_mover = FileMover(self.config, self.database)
sheets_sync = SheetsSyncService(self.config, self.database)
self.services: list[Service] = [
    self.drive_watcher, rip_queue, encode_queue, identifier, file_mover, sheets_sync
]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/dvdtoplex/main.py tests/test_main.py
git commit -m "feat: integrate Google Sheets sync service into application"
```

---

## Task 9: Update conftest.py Config for Tests

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Update Config dataclass in conftest**

Add the Google Sheets fields to the Config dataclass in `tests/conftest.py`:

```python
@dataclass
class Config:
    """Configuration dataclass for testing (mirrors src/dvdtoplex/config.py)."""

    pushover_user_key: str = ""
    pushover_api_token: str = ""
    tmdb_api_token: str = ""
    workspace_dir: Path = field(default_factory=lambda: Path.home() / "DVDWorkspace")
    plex_movies_dir: Path = field(
        default_factory=lambda: Path("/Volumes/Media8TB/Movies")
    )
    plex_tv_dir: Path = field(
        default_factory=lambda: Path("/Volumes/Media8TB/TV Shows")
    )
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    drive_poll_interval: float = 5.0
    auto_approve_threshold: float = 0.85
    google_sheets_credentials_file: Path | None = None
    google_sheets_spreadsheet_id: str | None = None
    sheets_sync_interval: int = 24
```

**Step 2: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add Google Sheets config fields to test fixtures"
```

---

## Task 10: Final Integration Test and Documentation

**Files:**
- Modify: `.env` (add example config)
- Update: `README-impl.md` or create setup instructions

**Step 1: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All PASS

**Step 2: Add example config to .env**

Add to `.env` (commented out):

```bash
# Google Sheets Sync (optional)
# GOOGLE_SHEETS_CREDENTIALS_FILE=/path/to/service-account.json
# GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id_here
# SHEETS_SYNC_INTERVAL=24
```

**Step 3: Commit**

```bash
git add .env
git commit -m "docs: add Google Sheets config examples to .env"
```

**Step 4: Final commit with all changes**

```bash
git log --oneline -10
```

Verify the feature is complete with all commits in place.

---

## Summary

This plan implements Google Sheets sync in 10 tasks:

1. Add gspread dependency
2. Add configuration options
3. Create Plex directory scanner
4. Create Google Sheets client
5. Create sync service
6. Add poster_path to wanted items
7. Update web API for poster_path
8. Integrate service into main app
9. Update test fixtures
10. Final integration and docs

Each task follows TDD: write failing test, implement, verify, commit.
