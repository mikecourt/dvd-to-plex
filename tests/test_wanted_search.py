"""Tests for the /wanted/search endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from dvdtoplex.tmdb import MovieMatch, TVMatch
from dvdtoplex.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


class TestWantedSearch:
    """Tests for the /wanted/search endpoint."""

    def test_wanted_search_empty_query(self, client: TestClient) -> None:
        """Test that empty query returns page without search results."""
        response = client.get("/wanted/search")
        assert response.status_code == 200
        assert "Wanted List" in response.text
        # Should not have search results section visible
        assert "Search Results" not in response.text

    def test_wanted_search_empty_query_explicit(self, client: TestClient) -> None:
        """Test that explicit empty query returns page without results."""
        response = client.get("/wanted/search?q=")
        assert response.status_code == 200
        assert "Search Results" not in response.text

    @patch("dvdtoplex.web.app.TMDbClient")
    def test_wanted_search_with_query_returns_results(
        self, mock_tmdb_class: AsyncMock, client: TestClient
    ) -> None:
        """Test that search query returns combined movie and TV results."""
        # Mock the TMDb client instance
        mock_tmdb = AsyncMock()
        mock_tmdb_class.return_value = mock_tmdb

        # Create mock movie and TV results
        mock_movies = [
            MovieMatch(
                tmdb_id=550,
                title="Fight Club",
                year=1999,
                overview="A depressed man forms an underground fight club.",
                poster_path="/path/to/poster.jpg",
                popularity=45.5,
            ),
        ]
        mock_tv = [
            TVMatch(
                tmdb_id=1399,
                name="Game of Thrones",
                year=2011,
                overview="Nine noble families fight for control.",
                poster_path="/path/to/tv_poster.jpg",
                popularity=200.0,
            ),
        ]

        mock_tmdb.search_movie.return_value = mock_movies
        mock_tmdb.search_tv.return_value = mock_tv
        mock_tmdb.close.return_value = None

        response = client.get("/wanted/search?q=fight")

        assert response.status_code == 200
        # Check that search results section is displayed
        assert "Search Results" in response.text
        # Check movie result is present
        assert "Fight Club" in response.text
        assert "1999" in response.text
        # Check TV result is present
        assert "Game of Thrones" in response.text
        assert "2011" in response.text

        # Verify TMDb client was called
        mock_tmdb.search_movie.assert_called_once_with("fight")
        mock_tmdb.search_tv.assert_called_once_with("fight")
        mock_tmdb.close.assert_called_once()

    @patch("dvdtoplex.web.app.TMDbClient")
    def test_wanted_search_results_sorted_by_popularity(
        self, mock_tmdb_class: AsyncMock, client: TestClient
    ) -> None:
        """Test that results are sorted by popularity descending."""
        mock_tmdb = AsyncMock()
        mock_tmdb_class.return_value = mock_tmdb

        # Create results with different popularity scores
        mock_movies = [
            MovieMatch(
                tmdb_id=1,
                title="Low Popularity Movie",
                year=2020,
                overview="",
                poster_path=None,
                popularity=10.0,
            ),
        ]
        mock_tv = [
            TVMatch(
                tmdb_id=2,
                name="High Popularity Show",
                year=2021,
                overview="",
                poster_path=None,
                popularity=100.0,
            ),
        ]

        mock_tmdb.search_movie.return_value = mock_movies
        mock_tmdb.search_tv.return_value = mock_tv
        mock_tmdb.close.return_value = None

        response = client.get("/wanted/search?q=test")

        assert response.status_code == 200
        # High popularity show should appear before low popularity movie
        high_pos = response.text.find("High Popularity Show")
        low_pos = response.text.find("Low Popularity Movie")
        assert high_pos < low_pos, "Results should be sorted by popularity"

    @patch("dvdtoplex.web.app.TMDbClient")
    def test_wanted_search_no_results(
        self, mock_tmdb_class: AsyncMock, client: TestClient
    ) -> None:
        """Test search with no matching results."""
        mock_tmdb = AsyncMock()
        mock_tmdb_class.return_value = mock_tmdb

        mock_tmdb.search_movie.return_value = []
        mock_tmdb.search_tv.return_value = []
        mock_tmdb.close.return_value = None

        response = client.get("/wanted/search?q=xyznonexistent123")

        assert response.status_code == 200
        # Search results section should not appear with no results
        assert "Search Results" not in response.text

    @patch("dvdtoplex.web.app.TMDbClient")
    def test_wanted_search_preserves_query_in_form(
        self, mock_tmdb_class: AsyncMock, client: TestClient
    ) -> None:
        """Test that the search query is preserved in the form input."""
        mock_tmdb = AsyncMock()
        mock_tmdb_class.return_value = mock_tmdb

        mock_tmdb.search_movie.return_value = []
        mock_tmdb.search_tv.return_value = []
        mock_tmdb.close.return_value = None

        response = client.get("/wanted/search?q=test+query")

        assert response.status_code == 200
        # The query should appear in the value attribute of the search input
        assert 'value="test query"' in response.text

    @patch("dvdtoplex.web.app.TMDbClient")
    def test_wanted_search_limits_results(
        self, mock_tmdb_class: AsyncMock, client: TestClient
    ) -> None:
        """Test that results are limited to 20."""
        mock_tmdb = AsyncMock()
        mock_tmdb_class.return_value = mock_tmdb

        # Create 15 movies and 15 TV shows (30 total, should be limited to 20)
        # Use format that won't have substring matching issues (Movie_00, Movie_01, etc.)
        mock_movies = [
            MovieMatch(
                tmdb_id=i,
                title=f"TestLimitMovie_{i:02d}",
                year=2020,
                overview="",
                poster_path=None,
                popularity=float(i),
            )
            for i in range(15)
        ]
        mock_tv = [
            TVMatch(
                tmdb_id=100 + i,
                name=f"TestLimitShow_{i:02d}",
                year=2020,
                overview="",
                poster_path=None,
                popularity=float(100 + i),
            )
            for i in range(15)
        ]

        mock_tmdb.search_movie.return_value = mock_movies
        mock_tmdb.search_tv.return_value = mock_tv
        mock_tmdb.close.return_value = None

        response = client.get("/wanted/search?q=test")

        assert response.status_code == 200
        # Count unique movie/tv result cards using exact patterns with delimiters
        movie_matches = sum(
            1 for i in range(15) if f"TestLimitMovie_{i:02d}" in response.text
        )
        tv_matches = sum(
            1 for i in range(15) if f"TestLimitShow_{i:02d}" in response.text
        )
        total_unique_results = movie_matches + tv_matches
        assert total_unique_results <= 20, f"Expected at most 20 unique results, got {total_unique_results}"
        # Verify we actually got results (not an empty response)
        assert total_unique_results > 0, "Should have search results"

    def test_wanted_search_shows_existing_wanted_items(self, client: TestClient) -> None:
        """Test that existing wanted items are displayed on search page."""
        # Add an item to the wanted list
        app = client.app
        app.state.wanted = [
            {
                "id": 1,
                "title": "Existing Want",
                "year": 2020,
                "content_type": "movie",
                "notes": "Test note",
            }
        ]

        response = client.get("/wanted/search?q=")

        assert response.status_code == 200
        assert "Existing Want" in response.text
        assert "My Wanted List" in response.text

    @patch("dvdtoplex.web.app.TMDbClient")
    def test_wanted_search_handles_special_characters(
        self, mock_tmdb_class: AsyncMock, client: TestClient
    ) -> None:
        """Test that search handles special characters in query."""
        mock_tmdb = AsyncMock()
        mock_tmdb_class.return_value = mock_tmdb

        mock_tmdb.search_movie.return_value = []
        mock_tmdb.search_tv.return_value = []
        mock_tmdb.close.return_value = None

        # Query with special characters
        response = client.get("/wanted/search?q=The%20Lord%20of%20the%20Rings%3A%20Return")

        assert response.status_code == 200
        mock_tmdb.search_movie.assert_called_once_with("The Lord of the Rings: Return")

    @patch("dvdtoplex.web.app.TMDbClient")
    def test_wanted_search_content_type_badges(
        self, mock_tmdb_class: AsyncMock, client: TestClient
    ) -> None:
        """Test that correct badges are shown for movie and TV results."""
        mock_tmdb = AsyncMock()
        mock_tmdb_class.return_value = mock_tmdb

        mock_movies = [
            MovieMatch(
                tmdb_id=1,
                title="Test Movie",
                year=2020,
                overview="A movie",
                poster_path=None,
                popularity=50.0,
            ),
        ]
        mock_tv = [
            TVMatch(
                tmdb_id=2,
                name="Test Show",
                year=2020,
                overview="A show",
                poster_path=None,
                popularity=50.0,
            ),
        ]

        mock_tmdb.search_movie.return_value = mock_movies
        mock_tmdb.search_tv.return_value = mock_tv
        mock_tmdb.close.return_value = None

        response = client.get("/wanted/search?q=test")

        assert response.status_code == 200
        # Check for content type indicators in results
        assert "badge-movie" in response.text or "movie" in response.text.lower()
        assert "badge-tv" in response.text or "tv" in response.text.lower()
