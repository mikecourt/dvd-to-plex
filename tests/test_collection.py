"""Tests for collection functionality including database and web routes."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from dvdtoplex.database import ContentType, Database
from dvdtoplex.web.app import create_app


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def client(db: Database) -> TestClient:
    """Create a test client with the database."""
    app = create_app(database=db)
    return TestClient(app)


class TestContentType:
    """Tests for ContentType enum."""

    def test_content_type_values(self) -> None:
        """ContentType enum should have expected values."""
        assert ContentType.UNKNOWN.value == "unknown"
        assert ContentType.MOVIE.value == "movie"
        assert ContentType.TV_SEASON.value == "tv_season"


class TestDatabaseCollection:
    """Tests for database collection operations."""

    @pytest.mark.asyncio
    async def test_add_movie_to_collection(self, db: Database) -> None:
        """Should add a movie to the collection."""
        item_id = await db.add_to_collection(
            content_type="movie",
            title="The Matrix",
            year=1999,
            tmdb_id=603,
            file_path="/movies/The Matrix (1999)/The Matrix (1999).mkv",
        )

        assert item_id > 0

        items = await db.get_collection()
        assert len(items) == 1
        assert items[0]["title"] == "The Matrix"
        assert items[0]["year"] == 1999
        assert items[0]["content_type"] == "movie"
        assert items[0]["tmdb_id"] == 603

    @pytest.mark.asyncio
    async def test_add_tv_season_to_collection(self, db: Database) -> None:
        """Should add a TV season to the collection."""
        item_id = await db.add_to_collection(
            content_type="tv_season",
            title="Breaking Bad",
            year=2008,
            tmdb_id=1396,
            file_path="/tv/Breaking Bad/Season 01/",
        )

        assert item_id > 0

        items = await db.get_collection()
        assert len(items) == 1
        assert items[0]["title"] == "Breaking Bad"
        assert items[0]["content_type"] == "tv_season"

    @pytest.mark.asyncio
    async def test_add_item_with_unknown_year(self, db: Database) -> None:
        """Should add an item with no year to the collection."""
        item_id = await db.add_to_collection(
            content_type="movie",
            title="Unknown Movie",
            year=None,
            tmdb_id=None,
            file_path="/movies/Unknown Movie/Unknown Movie.mkv",
        )

        assert item_id > 0

        items = await db.get_collection()
        assert len(items) == 1
        assert items[0]["year"] is None

    @pytest.mark.asyncio
    async def test_get_collection_ordered_by_date(self, db: Database) -> None:
        """Collection should be ordered by added_at descending."""
        await db.add_to_collection("movie", "First Movie", 2000, 1, "/path1")
        await db.add_to_collection("movie", "Second Movie", 2001, 2, "/path2")
        await db.add_to_collection("movie", "Third Movie", 2002, 3, "/path3")

        items = await db.get_collection()
        assert len(items) == 3
        # Most recent first
        assert items[0]["title"] == "Third Movie"
        assert items[2]["title"] == "First Movie"

    @pytest.mark.asyncio
    async def test_remove_from_collection(self, db: Database) -> None:
        """Should remove an item from the collection."""
        item_id = await db.add_to_collection(
            content_type="movie",
            title="To Be Removed",
            year=2020,
            tmdb_id=123,
            file_path="/path/to/movie.mkv",
        )

        result = await db.remove_from_collection(item_id)
        assert result is True

        items = await db.get_collection()
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_item(self, db: Database) -> None:
        """Should return False when removing nonexistent item."""
        result = await db.remove_from_collection(9999)
        assert result is False


class TestCollectionWebRoute:
    """Tests for the /collection web route."""

    @pytest.mark.asyncio
    async def test_collection_page_empty(
        self, db: Database, client: TestClient
    ) -> None:
        """Collection page should render with empty state."""
        response = client.get("/collection")
        assert response.status_code == 200
        assert "Your collection is empty" in response.text
        assert "Collection" in response.text

    @pytest.mark.asyncio
    async def test_collection_page_with_items(
        self, db: Database, client: TestClient
    ) -> None:
        """Collection page should display items with title, year, and badge."""
        # Add test items
        await db.add_to_collection("movie", "Inception", 2010, 27205, "/path1")
        await db.add_to_collection("tv_season", "The Office", 2005, 2316, "/path2")

        response = client.get("/collection")
        assert response.status_code == 200

        # Check title is displayed
        assert "Inception" in response.text
        assert "The Office" in response.text

        # Check year is displayed
        assert "2010" in response.text
        assert "2005" in response.text

        # Check content type badges are present
        assert "badge-movie" in response.text
        assert "badge-tv_season" in response.text
        assert "Movie" in response.text
        # Jinja2 title filter produces "Tv_season" (first letter of each word capitalized)
        assert "Tv_season" in response.text

    @pytest.mark.asyncio
    async def test_collection_page_with_unknown_year(
        self, db: Database, client: TestClient
    ) -> None:
        """Collection page should handle items with unknown year."""
        await db.add_to_collection("movie", "Mystery Film", None, None, "/path")

        response = client.get("/collection")
        assert response.status_code == 200
        assert "Mystery Film" in response.text
        assert "Unknown Year" in response.text

    @pytest.mark.asyncio
    async def test_collection_has_search_input(
        self, db: Database, client: TestClient
    ) -> None:
        """Collection page should have search input for filtering."""
        response = client.get("/collection")
        assert response.status_code == 200
        assert 'id="search-input"' in response.text
        assert "Search collection" in response.text

    @pytest.mark.asyncio
    async def test_collection_items_have_data_attributes(
        self, db: Database, client: TestClient
    ) -> None:
        """Collection items should have data attributes for search filtering."""
        await db.add_to_collection("movie", "Test Movie", 2023, 1, "/path")

        response = client.get("/collection")
        assert response.status_code == 200
        assert 'data-title="test movie"' in response.text
        assert 'data-year="2023"' in response.text


class TestCollectionBadgeStyling:
    """Tests for badge CSS classes in templates."""

    @pytest.mark.asyncio
    async def test_badge_classes_exist_in_base(
        self, db: Database, client: TestClient
    ) -> None:
        """Base template should include badge CSS classes."""
        # Add items with different content types to render badge classes
        await db.add_to_collection("movie", "Test Movie", 2023, 1, "/path1")
        await db.add_to_collection("tv_season", "Test Show", 2022, 2, "/path2")

        response = client.get("/collection")
        assert response.status_code == 200

        # Badge classes are rendered dynamically based on content type
        assert "badge-movie" in response.text
        assert "badge-tv_season" in response.text


class TestCollectionClientSideFiltering:
    """Tests for client-side search filtering functionality."""

    @pytest.mark.asyncio
    async def test_search_input_has_correct_attributes(
        self, db: Database, client: TestClient
    ) -> None:
        """Search input should have required attributes for filtering."""
        response = client.get("/collection")
        assert response.status_code == 200
        assert 'id="search-input"' in response.text
        assert 'class="form-input"' in response.text  # Template uses form-input class
        assert 'placeholder="Search collection' in response.text

    @pytest.mark.asyncio
    async def test_javascript_filter_event_listener(
        self, db: Database, client: TestClient
    ) -> None:
        """Template should include event listener for search input."""
        response = client.get("/collection")
        assert response.status_code == 200
        assert "addEventListener" in response.text
        assert "'input'" in response.text

    @pytest.mark.asyncio
    async def test_javascript_filter_logic(
        self, db: Database, client: TestClient
    ) -> None:
        """Template should include filter logic for title and year matching."""
        response = client.get("/collection")
        assert response.status_code == 200
        # Check for core filtering logic
        assert "toLowerCase()" in response.text
        assert "includes(query)" in response.text
        assert "dataset.title" in response.text
        assert "dataset.year" in response.text

    @pytest.mark.asyncio
    async def test_javascript_display_toggle(
        self, db: Database, client: TestClient
    ) -> None:
        """Template should toggle item visibility based on search."""
        response = client.get("/collection")
        assert response.status_code == 200
        assert "style.display" in response.text

    @pytest.mark.asyncio
    async def test_javascript_no_results_handling(
        self, db: Database, client: TestClient
    ) -> None:
        """Template should show/hide no-results message."""
        # Add an item so the no-results element is rendered
        await db.add_to_collection("movie", "Test Movie", 2023, 1, "/path")

        response = client.get("/collection")
        assert response.status_code == 200
        assert 'id="no-results"' in response.text
        # Template uses style.display instead of classList.toggle
        assert "noResults.style.display" in response.text
        assert "No items match your search" in response.text

    @pytest.mark.asyncio
    async def test_javascript_visible_count_update(
        self, db: Database, client: TestClient
    ) -> None:
        """Template should track visible item count during filtering."""
        response = client.get("/collection")
        assert response.status_code == 200
        # Template tracks visible count internally (not displayed in element)
        assert "visibleCount" in response.text
        assert "visibleCount++" in response.text

    @pytest.mark.asyncio
    async def test_collection_items_have_lowercase_data_title(
        self, db: Database, client: TestClient
    ) -> None:
        """Collection items should have lowercase data-title for case-insensitive search."""
        await db.add_to_collection("movie", "The MATRIX", 1999, 603, "/path")

        response = client.get("/collection")
        assert response.status_code == 200
        # Title should be lowercased in data-title attribute
        assert 'data-title="the matrix"' in response.text

    @pytest.mark.asyncio
    async def test_no_results_hidden_by_default(
        self, db: Database, client: TestClient
    ) -> None:
        """No-results message should be hidden by default."""
        # Add an item so the no-results element is rendered
        await db.add_to_collection("movie", "Test Movie", 2023, 1, "/path")

        response = client.get("/collection")
        assert response.status_code == 200
        # No-results is hidden by inline style, not CSS class
        assert 'id="no-results"' in response.text
        assert 'style="display: none' in response.text
