"""Tests for wanted list functionality."""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from dvdtoplex.database import Database


@pytest_asyncio.fixture
async def db() -> Database:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    database = Database(db_path)
    await database.connect()
    yield database
    await database.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_add_to_wanted(db: Database) -> None:
    """Test adding an item to the wanted list."""
    wanted_id = await db.add_to_wanted(
        content_type="movie",
        title="The Matrix",
        year=1999,
        tmdb_id=603,
        notes="Looking for original DVD release",
    )

    assert wanted_id > 0

    items = await db.get_wanted()
    assert len(items) == 1
    assert items[0]["title"] == "The Matrix"
    assert items[0]["year"] == 1999
    assert items[0]["content_type"] == "movie"
    assert items[0]["tmdb_id"] == 603
    assert items[0]["notes"] == "Looking for original DVD release"


@pytest.mark.asyncio
async def test_add_to_wanted_minimal(db: Database) -> None:
    """Test adding an item with only required fields."""
    wanted_id = await db.add_to_wanted(
        content_type="unknown",
        title="Some Movie",
    )

    assert wanted_id > 0

    items = await db.get_wanted()
    assert len(items) == 1
    assert items[0]["title"] == "Some Movie"
    assert items[0]["year"] is None
    assert items[0]["notes"] is None


@pytest.mark.asyncio
async def test_get_wanted_empty(db: Database) -> None:
    """Test getting wanted items when list is empty."""
    items = await db.get_wanted()
    assert items == []


@pytest.mark.asyncio
async def test_get_wanted_ordered_by_added_at(db: Database) -> None:
    """Test that wanted items are ordered by added_at DESC (newest first)."""
    await db.add_to_wanted(content_type="movie", title="First Movie")
    await db.add_to_wanted(content_type="movie", title="Second Movie")
    await db.add_to_wanted(content_type="movie", title="Third Movie")

    items = await db.get_wanted()
    assert len(items) == 3
    # Most recently added should be first
    assert items[0]["title"] == "Third Movie"
    assert items[1]["title"] == "Second Movie"
    assert items[2]["title"] == "First Movie"


@pytest.mark.asyncio
async def test_remove_from_wanted(db: Database) -> None:
    """Test removing an item from the wanted list."""
    wanted_id = await db.add_to_wanted(
        content_type="movie",
        title="To Be Removed",
    )

    items = await db.get_wanted()
    assert len(items) == 1

    result = await db.remove_from_wanted(wanted_id)
    assert result is True

    items = await db.get_wanted()
    assert len(items) == 0


@pytest.mark.asyncio
async def test_remove_from_wanted_not_found(db: Database) -> None:
    """Test removing a non-existent item returns False."""
    result = await db.remove_from_wanted(99999)
    assert result is False


@pytest.mark.asyncio
async def test_wanted_with_notes(db: Database) -> None:
    """Test that notes are stored and retrieved correctly."""
    notes = "Need the collector's edition with bonus features"
    await db.add_to_wanted(
        content_type="tv_season",
        title="Breaking Bad",
        year=2008,
        notes=notes,
    )

    items = await db.get_wanted()
    assert items[0]["notes"] == notes
    assert items[0]["content_type"] == "tv_season"
