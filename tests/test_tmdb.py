"""Tests for TMDb module."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dvdtoplex.tmdb import (
    MovieDetails,
    MovieMatch,
    TMDbClient,
    TVMatch,
    TVSeasonDetails,
    clean_disc_label,
)


class TestMovieMatch:
    """Tests for MovieMatch dataclass."""

    def test_create_movie_match(self) -> None:
        """Test creating a MovieMatch with all fields."""
        match = MovieMatch(
            tmdb_id=550,
            title="Fight Club",
            year=1999,
            overview="A depressed man suffering from insomnia meets a strange soap salesman.",
            poster_path="/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",
            popularity=61.416,
        )

        assert match.tmdb_id == 550
        assert match.title == "Fight Club"
        assert match.year == 1999
        assert match.overview == "A depressed man suffering from insomnia meets a strange soap salesman."
        assert match.poster_path == "/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg"
        assert match.popularity == 61.416

    def test_movie_match_with_none_poster(self) -> None:
        """Test creating a MovieMatch with no poster path."""
        match = MovieMatch(
            tmdb_id=12345,
            title="Unknown Movie",
            year=2020,
            overview="No description available.",
            poster_path=None,
            popularity=0.5,
        )

        assert match.tmdb_id == 12345
        assert match.poster_path is None

    def test_movie_match_equality(self) -> None:
        """Test that two MovieMatch instances with same data are equal."""
        match1 = MovieMatch(
            tmdb_id=550,
            title="Fight Club",
            year=1999,
            overview="A movie.",
            poster_path="/poster.jpg",
            popularity=61.416,
        )
        match2 = MovieMatch(
            tmdb_id=550,
            title="Fight Club",
            year=1999,
            overview="A movie.",
            poster_path="/poster.jpg",
            popularity=61.416,
        )

        assert match1 == match2


class TestTVMatch:
    """Tests for TVMatch dataclass."""

    def test_create_tv_match(self) -> None:
        """Test creating a TVMatch with all fields."""
        match = TVMatch(
            tmdb_id=1396,
            name="Breaking Bad",
            year=2008,
            overview="A high school chemistry teacher diagnosed with inoperable lung cancer.",
            poster_path="/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
            popularity=282.015,
        )

        assert match.tmdb_id == 1396
        assert match.name == "Breaking Bad"
        assert match.year == 2008
        assert match.overview == "A high school chemistry teacher diagnosed with inoperable lung cancer."
        assert match.poster_path == "/ggFHVNu6YYI5L9pCfOacjizRGt.jpg"
        assert match.popularity == 282.015

    def test_tv_match_with_none_poster(self) -> None:
        """Test creating a TVMatch with no poster path."""
        match = TVMatch(
            tmdb_id=99999,
            name="Unknown Show",
            year=2015,
            overview="No description.",
            poster_path=None,
            popularity=1.0,
        )

        assert match.tmdb_id == 99999
        assert match.poster_path is None

    def test_tv_match_equality(self) -> None:
        """Test that two TVMatch instances with same data are equal."""
        match1 = TVMatch(
            tmdb_id=1396,
            name="Breaking Bad",
            year=2008,
            overview="A show.",
            poster_path="/poster.jpg",
            popularity=282.015,
        )
        match2 = TVMatch(
            tmdb_id=1396,
            name="Breaking Bad",
            year=2008,
            overview="A show.",
            poster_path="/poster.jpg",
            popularity=282.015,
        )

        assert match1 == match2


class TestMovieAndTVMatchDifference:
    """Tests to ensure MovieMatch and TVMatch are distinct types."""

    def test_movie_and_tv_are_different_types(self) -> None:
        """Test that MovieMatch and TVMatch are distinct types."""
        movie = MovieMatch(
            tmdb_id=550,
            title="Fight Club",
            year=1999,
            overview="A movie.",
            poster_path=None,
            popularity=61.416,
        )
        tv = TVMatch(
            tmdb_id=550,
            name="Fight Club",
            year=1999,
            overview="A movie.",
            poster_path=None,
            popularity=61.416,
        )

        assert type(movie) is not type(tv)
        assert isinstance(movie, MovieMatch)
        assert isinstance(tv, TVMatch)
        assert not isinstance(movie, TVMatch)
        assert not isinstance(tv, MovieMatch)


class TestMovieDetails:
    """Tests for MovieDetails dataclass."""

    def test_create_movie_details(self) -> None:
        """Test creating MovieDetails with all fields."""
        details = MovieDetails(
            tmdb_id=550,
            title="Fight Club",
            year=1999,
            overview="A depressed man suffers from insomnia.",
            poster_path="/poster.jpg",
            popularity=61.416,
            runtime=139,
            genres=["Drama", "Thriller"],
            tagline="Mischief. Mayhem. Soap.",
        )

        assert details.tmdb_id == 550
        assert details.title == "Fight Club"
        assert details.year == 1999
        assert details.runtime == 139
        assert details.genres == ["Drama", "Thriller"]
        assert details.tagline == "Mischief. Mayhem. Soap."

    def test_movie_details_with_none_runtime(self) -> None:
        """Test MovieDetails with no runtime."""
        details = MovieDetails(
            tmdb_id=12345,
            title="Unknown",
            year=None,
            overview="",
            poster_path=None,
            popularity=0.0,
            runtime=None,
            genres=[],
            tagline="",
        )

        assert details.runtime is None
        assert details.genres == []


class TestTVSeasonDetails:
    """Tests for TVSeasonDetails dataclass."""

    def test_create_tv_season_details(self) -> None:
        """Test creating TVSeasonDetails with all fields."""
        episodes: list[dict[str, Any]] = [
            {
                "episode_number": 1,
                "name": "Pilot",
                "overview": "First episode.",
                "air_date": "2008-01-20",
                "runtime": 58,
            },
            {
                "episode_number": 2,
                "name": "Cat's in the Bag...",
                "overview": "Second episode.",
                "air_date": "2008-01-27",
                "runtime": 48,
            },
        ]

        details = TVSeasonDetails(
            tmdb_id=1396,
            show_name="Breaking Bad",
            season_number=1,
            name="Season 1",
            overview="The first season of Breaking Bad.",
            poster_path="/poster.jpg",
            air_date="2008-01-20",
            episodes=episodes,
        )

        assert details.tmdb_id == 1396
        assert details.show_name == "Breaking Bad"
        assert details.season_number == 1
        assert details.name == "Season 1"
        assert len(details.episodes) == 2
        assert details.episodes[0]["name"] == "Pilot"


class TestCleanDiscLabel:
    """Tests for clean_disc_label function."""

    def test_removes_disc_number(self) -> None:
        """Test that disc numbers are removed."""
        assert clean_disc_label("GODFATHER_DISC_1") == "godfather"
        assert clean_disc_label("THE_MATRIX_DISC_2") == "the matrix"
        assert clean_disc_label("LOTR_DISC1") == "lotr"

    def test_removes_dvd_suffix(self) -> None:
        """Test that DVD suffix is removed."""
        assert clean_disc_label("THE_DARK_KNIGHT_DVD") == "the dark knight"
        assert clean_disc_label("DVD_INCEPTION") == "inception"

    def test_removes_widescreen(self) -> None:
        """Test that WIDESCREEN suffix is removed."""
        assert clean_disc_label("INCEPTION_WIDESCREEN") == "inception"
        assert clean_disc_label("AVATAR_WS") == "avatar"

    def test_removes_region_codes(self) -> None:
        """Test that region codes are removed."""
        assert clean_disc_label("JAWS_R1") == "jaws"
        assert clean_disc_label("ALIENS_REGION_2") == "aliens"

    def test_handles_multiple_patterns(self) -> None:
        """Test removal of chained patterns."""
        assert clean_disc_label("MOVIE_WIDESCREEN_R1") == "movie"
        assert clean_disc_label("FILM_DISC_1_DVD") == "film"

    def test_converts_to_lowercase(self) -> None:
        """Test that result is lowercase."""
        assert clean_disc_label("THE_MATRIX") == "the matrix"
        assert clean_disc_label("AVATAR") == "avatar"

    def test_replaces_underscores_with_spaces(self) -> None:
        """Test that underscores become spaces."""
        assert clean_disc_label("STAR_WARS") == "star wars"
        assert clean_disc_label("LORD_OF_THE_RINGS") == "lord of the rings"

    def test_normalizes_whitespace(self) -> None:
        """Test that multiple spaces are collapsed."""
        assert clean_disc_label("THE__MOVIE") == "the movie"
        assert clean_disc_label("MOVIE   NAME") == "movie name"


class TestTMDbClient:
    """Tests for TMDbClient class."""

    @pytest.fixture
    def client(self) -> TMDbClient:
        """Create a TMDbClient instance for testing."""
        return TMDbClient(api_token="test_token")

    def test_client_initialization(self, client: TMDbClient) -> None:
        """Test that client initializes with correct token."""
        assert client.api_token == "test_token"
        assert client._client is None

    def test_extract_year_valid(self, client: TMDbClient) -> None:
        """Test year extraction from valid date string."""
        assert client._extract_year("1999-10-15") == 1999
        assert client._extract_year("2023-01-01") == 2023

    def test_extract_year_none(self, client: TMDbClient) -> None:
        """Test year extraction from None or empty string."""
        assert client._extract_year(None) is None
        assert client._extract_year("") is None
        assert client._extract_year("abc") is None

    @pytest.mark.asyncio
    async def test_search_movie(self, client: TMDbClient) -> None:
        """Test movie search returns MovieMatch results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 550,
                    "title": "Fight Club",
                    "release_date": "1999-10-15",
                    "overview": "A depressed man...",
                    "poster_path": "/poster.jpg",
                    "popularity": 61.416,
                },
                {
                    "id": 551,
                    "title": "Fight Club 2",
                    "release_date": "2020-01-01",
                    "overview": "A sequel...",
                    "poster_path": None,
                    "popularity": 10.0,
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):
            results = await client.search_movie("Fight Club")

        assert len(results) == 2
        assert isinstance(results[0], MovieMatch)
        assert results[0].tmdb_id == 550
        assert results[0].title == "Fight Club"
        assert results[0].year == 1999
        assert results[1].poster_path is None

    @pytest.mark.asyncio
    async def test_search_movie_with_year(self, client: TMDbClient) -> None:
        """Test movie search with year parameter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):
            await client.search_movie("Test", year=2020)

        mock_http_client.get.assert_called_once()
        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["year"] == 2020

    @pytest.mark.asyncio
    async def test_search_tv(self, client: TMDbClient) -> None:
        """Test TV search returns TVMatch results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1396,
                    "name": "Breaking Bad",
                    "first_air_date": "2008-01-20",
                    "overview": "A chemistry teacher...",
                    "poster_path": "/poster.jpg",
                    "popularity": 282.015,
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):
            results = await client.search_tv("Breaking Bad")

        assert len(results) == 1
        assert isinstance(results[0], TVMatch)
        assert results[0].tmdb_id == 1396
        assert results[0].name == "Breaking Bad"
        assert results[0].year == 2008

    @pytest.mark.asyncio
    async def test_search_tv_with_year(self, client: TMDbClient) -> None:
        """Test TV search with year parameter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):
            await client.search_tv("Test", year=2015)

        mock_http_client.get.assert_called_once()
        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["first_air_date_year"] == 2015

    @pytest.mark.asyncio
    async def test_get_movie_details(self, client: TMDbClient) -> None:
        """Test getting movie details returns MovieDetails."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": 550,
            "title": "Fight Club",
            "release_date": "1999-10-15",
            "overview": "A depressed man...",
            "poster_path": "/poster.jpg",
            "popularity": 61.416,
            "runtime": 139,
            "genres": [{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}],
            "tagline": "Mischief. Mayhem. Soap.",
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):
            details = await client.get_movie_details(550)

        assert isinstance(details, MovieDetails)
        assert details.tmdb_id == 550
        assert details.title == "Fight Club"
        assert details.runtime == 139
        assert details.genres == ["Drama", "Thriller"]
        assert details.tagline == "Mischief. Mayhem. Soap."

    @pytest.mark.asyncio
    async def test_get_tv_season(self, client: TMDbClient) -> None:
        """Test getting TV season details returns TVSeasonDetails."""
        mock_show_response = MagicMock()
        mock_show_response.json.return_value = {"name": "Breaking Bad"}
        mock_show_response.raise_for_status = MagicMock()

        mock_season_response = MagicMock()
        mock_season_response.json.return_value = {
            "name": "Season 1",
            "overview": "The first season.",
            "poster_path": "/season1.jpg",
            "air_date": "2008-01-20",
            "episodes": [
                {
                    "episode_number": 1,
                    "name": "Pilot",
                    "overview": "First episode.",
                    "air_date": "2008-01-20",
                    "runtime": 58,
                },
            ],
        }
        mock_season_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(
            side_effect=[mock_show_response, mock_season_response]
        )

        with patch.object(client, "_get_client", return_value=mock_http_client):
            details = await client.get_tv_season(1396, 1)

        assert isinstance(details, TVSeasonDetails)
        assert details.tmdb_id == 1396
        assert details.show_name == "Breaking Bad"
        assert details.season_number == 1
        assert details.name == "Season 1"
        assert len(details.episodes) == 1
        assert details.episodes[0]["name"] == "Pilot"

    @pytest.mark.asyncio
    async def test_search_movie_limits_to_10_results(self, client: TMDbClient) -> None:
        """Test that search_movie returns at most 10 results."""
        mock_response = MagicMock()
        # Return 15 results from API
        mock_response.json.return_value = {
            "results": [
                {
                    "id": i,
                    "title": f"Movie {i}",
                    "release_date": "2020-01-01",
                    "overview": "",
                    "poster_path": None,
                    "popularity": float(i),
                }
                for i in range(15)
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):
            results = await client.search_movie("Test")

        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_search_tv_limits_to_10_results(self, client: TMDbClient) -> None:
        """Test that search_tv returns at most 10 results."""
        mock_response = MagicMock()
        # Return 15 results from API
        mock_response.json.return_value = {
            "results": [
                {
                    "id": i,
                    "name": f"Show {i}",
                    "first_air_date": "2020-01-01",
                    "overview": "",
                    "poster_path": None,
                    "popularity": float(i),
                }
                for i in range(15)
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):
            results = await client.search_tv("Test")

        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_close_client(self, client: TMDbClient) -> None:
        """Test closing the HTTP client."""
        mock_http_client = AsyncMock()
        mock_http_client.aclose = AsyncMock()
        client._client = mock_http_client

        await client.close()

        mock_http_client.aclose.assert_called_once()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_client_when_none(self, client: TMDbClient) -> None:
        """Test closing when client is None does nothing."""
        assert client._client is None
        await client.close()  # Should not raise
        assert client._client is None
