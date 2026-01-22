"""Database module with async SQLite operations for DVD to Plex pipeline."""

from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class JobStatus(Enum):
    """Status of a ripping/encoding job."""

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
    ARCHIVED = "archived"


class ContentType(Enum):
    """Type of content on a disc."""

    UNKNOWN = "unknown"
    MOVIE = "movie"
    TV_SEASON = "tv_season"


class RipMode(Enum):
    """Mode for ripping and identification strategy."""

    MOVIE = "movie"  # TMDb movie search, output to Movies folder
    TV = "tv"  # TMDb TV search, output to TV Shows folder
    HOME_MOVIES = "home_movies"  # Skip TMDb, use disc label, output to Home Movies
    OTHER = "other"  # Skip TMDb, use disc label, output to Other folder


@dataclass
class Job:
    """Represents a ripping/encoding job."""

    id: int
    drive_id: str
    disc_label: str
    content_type: ContentType
    status: JobStatus
    identified_title: str | None
    identified_year: int | None
    tmdb_id: int | None
    confidence: float | None
    poster_path: str | None
    rip_path: str | None
    encode_path: str | None
    final_path: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    def __getitem__(self, key: str) -> Any:
        """Support dict-style access for backwards compatibility with tests."""
        value = getattr(self, key)
        # Convert enums to their string values for dict-style access
        if isinstance(value, Enum):
            return value.value
        return value


@dataclass
class TVSeason:
    """Represents a TV season."""

    id: int
    job_id: int
    show_title: str
    season_number: int
    tmdb_show_id: int | None
    created_at: datetime


@dataclass
class Episode:
    """Represents a TV episode."""

    id: int
    season_id: int
    episode_number: int
    title: str | None
    rip_path: str | None
    encode_path: str | None
    final_path: str | None


@dataclass
class CollectionItem:
    """Represents an item in the user's collection."""

    id: int
    title: str
    year: int | None
    content_type: ContentType
    tmdb_id: int | None
    file_path: str
    added_at: datetime


@dataclass
class WantedItem:
    """Represents an item in the user's wanted list."""

    id: int
    title: str
    year: int | None
    content_type: ContentType
    tmdb_id: int | None
    notes: str | None
    added_at: datetime

    def __getitem__(self, key: str) -> Any:
        """Support dict-style access for backwards compatibility with tests."""
        value = getattr(self, key)
        # Convert enums to their string values for dict-style access
        if isinstance(value, Enum):
            return value.value
        return value


@dataclass
class Setting:
    """Represents a configuration setting."""

    key: str
    value: str


class Database:
    """Async SQLite database for the DVD to Plex pipeline."""

    def __init__(self, db_path: str | Path) -> None:
        """Initialize database with the given path.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and create tables if needed."""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._create_tables()
        await self._run_migrations()
        await self._create_indexes()

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def initialize(self) -> None:
        """Initialize the database connection.

        This is an alias for connect() provided for API consistency.
        """
        await self.connect()

    @property
    def is_closed(self) -> bool:
        """Check if the database connection is closed.

        Returns:
            True if the connection is closed or was never opened.
        """
        return self._connection is None

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the database connection, raising if not connected."""
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def _create_tables(self) -> None:
        """Create all database tables if they don't exist."""
        await self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drive_id TEXT NOT NULL,
                disc_label TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'unknown',
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tv_seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                show_title TEXT NOT NULL,
                season_number INTEGER NOT NULL,
                tmdb_show_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL REFERENCES tv_seasons(id) ON DELETE CASCADE,
                episode_number INTEGER NOT NULL,
                title TEXT,
                rip_path TEXT,
                encode_path TEXT,
                final_path TEXT
            );

            CREATE TABLE IF NOT EXISTS collection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                year INTEGER,
                content_type TEXT NOT NULL DEFAULT 'movie',
                tmdb_id INTEGER,
                file_path TEXT NOT NULL,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS wanted (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                year INTEGER,
                content_type TEXT NOT NULL DEFAULT 'movie',
                tmdb_id INTEGER,
                notes TEXT,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        await self.connection.commit()

    async def _run_migrations(self) -> None:
        """Run database migrations for schema changes."""
        # Check if poster_path column exists in jobs table
        cursor = await self.connection.execute("PRAGMA table_info(jobs)")
        columns = await cursor.fetchall()
        column_names = {col["name"] for col in columns}

        if "poster_path" not in column_names:
            await self.connection.execute(
                "ALTER TABLE jobs ADD COLUMN poster_path TEXT"
            )
            await self.connection.commit()

    async def _create_indexes(self) -> None:
        """Create database indexes for common queries."""
        await self.connection.executescript("""
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_drive_id ON jobs(drive_id);
        """)
        await self.connection.commit()

    # Job operations

    async def create_job(
        self,
        drive_id: str,
        disc_label: str,
        content_type: ContentType = ContentType.UNKNOWN,
    ) -> Job:
        """Create a new job and return it.

        Args:
            drive_id: Identifier of the DVD drive.
            disc_label: Label of the disc.
            content_type: Type of content on the disc.

        Returns:
            The created job.
        """
        cursor = await self.connection.execute(
            """
            INSERT INTO jobs (drive_id, disc_label, content_type, status)
            VALUES (?, ?, ?, ?)
            """,
            (drive_id, disc_label, content_type.value, JobStatus.PENDING.value),
        )
        await self.connection.commit()
        job_id = cursor.lastrowid or 0
        job = await self.get_job(job_id)
        if job is None:
            raise RuntimeError(f"Failed to create job {job_id}")
        return job

    async def get_job(self, job_id: int) -> Job | None:
        """Get a job by ID.

        Args:
            job_id: The job ID.

        Returns:
            The job or None if not found.
        """
        cursor = await self.connection.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_job(row) if row else None

    async def get_all_jobs(self) -> list[Job]:
        """Get all jobs from the database.

        Returns:
            List of all jobs, ordered by ID descending.
        """
        cursor = await self.connection.execute("SELECT * FROM jobs ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]

    async def get_jobs_by_status(self, status: JobStatus) -> list[Job]:
        """Get all jobs with a specific status.

        Args:
            status: The job status to filter by.

        Returns:
            List of matching jobs.
        """
        cursor = await self.connection.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC",
            (status.value,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]

    async def get_pending_jobs(self) -> list[Job]:
        """Get all pending jobs.

        Returns:
            List of pending jobs ordered by creation time.
        """
        return await self.get_jobs_by_status(JobStatus.PENDING)

    async def get_jobs_by_drive(self, drive_id: str) -> list[Job]:
        """Get all jobs for a specific drive.

        Args:
            drive_id: The drive identifier.

        Returns:
            List of matching jobs.
        """
        cursor = await self.connection.execute(
            "SELECT * FROM jobs WHERE drive_id = ? ORDER BY created_at DESC",
            (drive_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]

    async def get_recent_jobs(
        self, limit: int = 10, exclude_archived: bool = False
    ) -> list[Job]:
        """Get the most recent jobs.

        Args:
            limit: Maximum number of jobs to return.
            exclude_archived: If True, exclude jobs with ARCHIVED status.

        Returns:
            List of recent jobs.
        """
        if exclude_archived:
            query = """
                SELECT * FROM jobs
                WHERE status != 'archived'
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            """
        else:
            query = """
                SELECT * FROM jobs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            """
        cursor = await self.connection.execute(query, (limit,))
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]

    async def get_pending_job_for_drive(self, drive_id: str) -> Job | None:
        """Get any active (pending or ripping) job for a specific drive.

        Args:
            drive_id: The drive identifier.

        Returns:
            An active job for the drive, or None if none found.
        """
        cursor = await self.connection.execute(
            """
            SELECT * FROM jobs
            WHERE drive_id = ? AND status IN (?, ?)
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (drive_id, JobStatus.PENDING.value, JobStatus.RIPPING.value),
        )
        row = await cursor.fetchone()
        return self._row_to_job(row) if row else None

    async def update_job_status(
        self,
        job_id: int,
        status: JobStatus,
        error_message: str | None = None,
        rip_path: str | None = None,
        encode_path: str | None = None,
    ) -> None:
        """Update a job's status.

        Args:
            job_id: The job ID.
            status: The new status.
            error_message: Optional error message (for failed status).
            rip_path: Optional path to ripped file.
            encode_path: Optional path to encoded file.
        """
        await self.connection.execute(
            """
            UPDATE jobs
            SET status = ?,
                error_message = COALESCE(?, error_message),
                rip_path = COALESCE(?, rip_path),
                encode_path = COALESCE(?, encode_path),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status.value, error_message, rip_path, encode_path, job_id),
        )
        await self.connection.commit()

    async def update_job_identification(
        self,
        job_id: int,
        content_type: ContentType,
        title: str,
        year: int | None,
        tmdb_id: int | None,
        confidence: float,
        poster_path: str | None = None,
    ) -> None:
        """Update a job's identification information.

        Args:
            job_id: The job ID.
            content_type: The identified content type.
            title: The identified title.
            year: The release year.
            tmdb_id: The TMDb ID.
            confidence: The confidence score (0.0 to 1.0).
            poster_path: The TMDb poster path (e.g., "/abc123.jpg").
        """
        await self.connection.execute(
            """
            UPDATE jobs
            SET content_type = ?, identified_title = ?, identified_year = ?,
                tmdb_id = ?, confidence = ?, poster_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (content_type.value, title, year, tmdb_id, confidence, poster_path, job_id),
        )
        await self.connection.commit()

    async def update_job_rip_path(self, job_id: int, rip_path: str) -> None:
        """Update a job's rip path.

        Args:
            job_id: The job ID.
            rip_path: Path to the ripped file.
        """
        await self.connection.execute(
            """
            UPDATE jobs
            SET rip_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (rip_path, job_id),
        )
        await self.connection.commit()

    async def update_job_encode_path(self, job_id: int, encode_path: str) -> None:
        """Update a job's encode path.

        Args:
            job_id: The job ID.
            encode_path: Path to the encoded file.
        """
        await self.connection.execute(
            """
            UPDATE jobs
            SET encode_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (encode_path, job_id),
        )
        await self.connection.commit()

    async def update_job_final_path(self, job_id: int, final_path: str) -> None:
        """Update a job's final path in the Plex library.

        Args:
            job_id: The job ID.
            final_path: Path to the final file in Plex library.
        """
        await self.connection.execute(
            """
            UPDATE jobs
            SET final_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (final_path, job_id),
        )
        await self.connection.commit()

    def _row_to_job(self, row: aiosqlite.Row) -> Job:
        """Convert a database row to a Job object."""
        return Job(
            id=row["id"],
            drive_id=row["drive_id"],
            disc_label=row["disc_label"],
            content_type=ContentType(row["content_type"]),
            status=JobStatus(row["status"]),
            identified_title=row["identified_title"],
            identified_year=row["identified_year"],
            tmdb_id=row["tmdb_id"],
            confidence=row["confidence"],
            poster_path=row["poster_path"],
            rip_path=row["rip_path"],
            encode_path=row["encode_path"],
            final_path=row["final_path"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # TV Season operations

    async def create_tv_season(
        self,
        job_id: int,
        show_title: str,
        season_number: int,
        tmdb_show_id: int | None = None,
    ) -> int:
        """Create a TV season record.

        Args:
            job_id: The associated job ID.
            show_title: Title of the TV show.
            season_number: Season number.
            tmdb_show_id: Optional TMDb show ID.

        Returns:
            The ID of the created TV season.
        """
        cursor = await self.connection.execute(
            """
            INSERT INTO tv_seasons (job_id, show_title, season_number, tmdb_show_id)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, show_title, season_number, tmdb_show_id),
        )
        await self.connection.commit()
        return cursor.lastrowid or 0

    async def get_tv_season(self, season_id: int) -> TVSeason | None:
        """Get a TV season by ID.

        Args:
            season_id: The TV season ID.

        Returns:
            The TV season or None if not found.
        """
        cursor = await self.connection.execute(
            "SELECT * FROM tv_seasons WHERE id = ?", (season_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return TVSeason(
            id=row["id"],
            job_id=row["job_id"],
            show_title=row["show_title"],
            season_number=row["season_number"],
            tmdb_show_id=row["tmdb_show_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def get_tv_seasons_by_job(self, job_id: int) -> list[TVSeason]:
        """Get all TV seasons for a job.

        Args:
            job_id: The job ID.

        Returns:
            List of TV seasons.
        """
        cursor = await self.connection.execute(
            "SELECT * FROM tv_seasons WHERE job_id = ? ORDER BY season_number",
            (job_id,),
        )
        rows = await cursor.fetchall()
        return [
            TVSeason(
                id=row["id"],
                job_id=row["job_id"],
                show_title=row["show_title"],
                season_number=row["season_number"],
                tmdb_show_id=row["tmdb_show_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    # Episode operations

    async def create_episode(
        self,
        season_id: int,
        episode_number: int,
        title: str | None = None,
    ) -> int:
        """Create an episode record.

        Args:
            season_id: The TV season ID.
            episode_number: Episode number.
            title: Optional episode title.

        Returns:
            The ID of the created episode.
        """
        cursor = await self.connection.execute(
            """
            INSERT INTO episodes (season_id, episode_number, title)
            VALUES (?, ?, ?)
            """,
            (season_id, episode_number, title),
        )
        await self.connection.commit()
        return cursor.lastrowid or 0

    async def get_episodes_by_season(self, season_id: int) -> list[Episode]:
        """Get all episodes for a TV season.

        Args:
            season_id: The TV season ID.

        Returns:
            List of episodes.
        """
        cursor = await self.connection.execute(
            "SELECT * FROM episodes WHERE season_id = ? ORDER BY episode_number",
            (season_id,),
        )
        rows = await cursor.fetchall()
        return [
            Episode(
                id=row["id"],
                season_id=row["season_id"],
                episode_number=row["episode_number"],
                title=row["title"],
                rip_path=row["rip_path"],
                encode_path=row["encode_path"],
                final_path=row["final_path"],
            )
            for row in rows
        ]

    async def update_episode_paths(
        self,
        episode_id: int,
        rip_path: str | None = None,
        encode_path: str | None = None,
        final_path: str | None = None,
    ) -> None:
        """Update episode file paths.

        Args:
            episode_id: The episode ID.
            rip_path: Optional rip path.
            encode_path: Optional encode path.
            final_path: Optional final path.
        """
        updates: list[str] = []
        params: list[Any] = []

        if rip_path is not None:
            updates.append("rip_path = ?")
            params.append(rip_path)
        if encode_path is not None:
            updates.append("encode_path = ?")
            params.append(encode_path)
        if final_path is not None:
            updates.append("final_path = ?")
            params.append(final_path)

        if updates:
            params.append(episode_id)
            await self.connection.execute(
                f"UPDATE episodes SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await self.connection.commit()

    # Collection operations

    async def add_to_collection(
        self,
        content_type: str | ContentType,
        title: str,
        year: int | None,
        tmdb_id: int | None,
        file_path: str,
    ) -> int:
        """Add an item to the collection.

        Args:
            content_type: Type of content (string or ContentType enum).
            title: Title of the item.
            year: Optional release year.
            tmdb_id: Optional TMDb ID.
            file_path: Path to the file.

        Returns:
            The ID of the created collection item.
        """
        # Convert string to ContentType enum if needed
        if isinstance(content_type, str):
            content_type_value = content_type
        else:
            content_type_value = content_type.value

        cursor = await self.connection.execute(
            """
            INSERT INTO collection (title, year, content_type, tmdb_id, file_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, year, content_type_value, tmdb_id, file_path),
        )
        await self.connection.commit()
        return cursor.lastrowid or 0

    async def get_collection(self) -> list[dict[str, Any]]:
        """Get all items in the collection.

        Returns:
            List of collection items as dicts, ordered by id descending (most recent first).
        """
        cursor = await self.connection.execute(
            "SELECT * FROM collection ORDER BY id DESC"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "year": row["year"],
                "content_type": row["content_type"],
                "tmdb_id": row["tmdb_id"],
                "file_path": row["file_path"],
                "added_at": datetime.fromisoformat(row["added_at"]),
            }
            for row in rows
        ]

    async def remove_from_collection(self, item_id: int) -> bool:
        """Remove an item from the collection.

        Args:
            item_id: The ID of the item to remove.

        Returns:
            True if the item was removed, False if not found.
        """
        cursor = await self.connection.execute(
            "DELETE FROM collection WHERE id = ?", (item_id,)
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    async def get_collection_item(self, item_id: int) -> CollectionItem | None:
        """Get a collection item by ID.

        Args:
            item_id: The collection item ID.

        Returns:
            The collection item or None if not found.
        """
        cursor = await self.connection.execute(
            "SELECT * FROM collection WHERE id = ?", (item_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return CollectionItem(
            id=row["id"],
            title=row["title"],
            year=row["year"],
            content_type=ContentType(row["content_type"]),
            tmdb_id=row["tmdb_id"],
            file_path=row["file_path"],
            added_at=datetime.fromisoformat(row["added_at"]),
        )

    # Wanted list operations

    async def add_to_wanted(
        self,
        title: str,
        year: int | None = None,
        content_type: ContentType | str = ContentType.MOVIE,
        tmdb_id: int | None = None,
        notes: str | None = None,
    ) -> int:
        """Add an item to the wanted list.

        Args:
            title: Title of the item.
            year: Optional release year.
            content_type: Type of content (string or ContentType enum).
            tmdb_id: Optional TMDb ID.
            notes: Optional notes.

        Returns:
            The ID of the created wanted item.
        """
        # Handle string or enum for content_type
        content_type_value = (
            content_type.value if isinstance(content_type, ContentType) else content_type
        )
        cursor = await self.connection.execute(
            """
            INSERT INTO wanted (title, year, content_type, tmdb_id, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, year, content_type_value, tmdb_id, notes),
        )
        await self.connection.commit()
        return cursor.lastrowid or 0

    async def get_wanted(self) -> list[WantedItem]:
        """Get all items in the wanted list.

        Returns:
            List of wanted items.
        """
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
                notes=row["notes"],
                added_at=datetime.fromisoformat(row["added_at"]),
            )
            for row in rows
        ]

    async def get_wanted_item(self, item_id: int) -> WantedItem | None:
        """Get a wanted item by ID.

        Args:
            item_id: The wanted item ID.

        Returns:
            The wanted item or None if not found.
        """
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
            notes=row["notes"],
            added_at=datetime.fromisoformat(row["added_at"]),
        )

    async def remove_from_wanted(self, item_id: int) -> bool:
        """Remove an item from the wanted list.

        Args:
            item_id: The wanted item ID.

        Returns:
            True if the item was removed, False if not found.
        """
        cursor = await self.connection.execute(
            "DELETE FROM wanted WHERE id = ?", (item_id,)
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    # Settings operations

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Get a setting value.

        Args:
            key: The setting key.
            default: Default value if not found.

        Returns:
            The setting value or default.
        """
        cursor = await self.connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        """Set a setting value.

        Args:
            key: The setting key.
            value: The setting value.
        """
        await self.connection.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self.connection.commit()

    async def get_all_settings(self) -> dict[str, str]:
        """Get all settings as a dictionary.

        Returns:
            Dictionary of settings.
        """
        cursor = await self.connection.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}
