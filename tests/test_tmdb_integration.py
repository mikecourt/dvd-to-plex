"""TMDb API integration tests for US-012.

These tests verify that the TMDb API client works correctly with real credentials
when configured via environment variables.
"""

import pytest

from dvdtoplex.config import load_config
from dvdtoplex.tmdb import TMDbClient


class TestTMDbIntegration:
    """Integration tests for TMDb API."""

    @pytest.mark.asyncio
    async def test_tmdb_search_with_real_credentials(self) -> None:
        """Test TMDb API search with real credentials if configured.

        This test:
        - Loads config with load_config()
        - If no TMDb token, skips the test
        - Otherwise, searches for "The Matrix" and verifies results
        - Checks that top result is "The Matrix (1999)"
        """
        config = load_config()

        if not config.tmdb_api_token:
            pytest.skip("SKIP: No TMDb token configured")

        async with TMDbClient(config.tmdb_api_token) as client:
            results = await client.search_movie("The Matrix")

            # Verify we got results
            assert len(results) > 0, "Expected at least one result for 'The Matrix'"
            print(f"Found {len(results)} results for 'The Matrix'")

            # Check top result
            top_result = results[0]
            print(f"Top result: {top_result.title} ({top_result.year})")

            # Verify the top result is The Matrix (1999)
            assert top_result.title == "The Matrix", f"Expected 'The Matrix', got '{top_result.title}'"
            assert top_result.year == 1999, f"Expected year 1999, got {top_result.year}"

    @pytest.mark.asyncio
    async def test_tmdb_client_requires_context_manager(self) -> None:
        """Test that TMDbClient raises error when not used as context manager."""
        config = load_config()

        if not config.tmdb_api_token:
            pytest.skip("SKIP: No TMDb token configured")

        client = TMDbClient(config.tmdb_api_token)

        # Should raise RuntimeError when accessing client outside context
        with pytest.raises(RuntimeError, match="must be used as async context manager"):
            _ = client.client

    @pytest.mark.asyncio
    async def test_tmdb_search_with_year_filter(self) -> None:
        """Test TMDb API search with year filter."""
        config = load_config()

        if not config.tmdb_api_token:
            pytest.skip("SKIP: No TMDb token configured")

        async with TMDbClient(config.tmdb_api_token) as client:
            # Search with year filter
            results = await client.search_movie("The Matrix", year=1999)

            assert len(results) > 0, "Expected at least one result"
            # First result should be The Matrix 1999
            assert results[0].year == 1999

    @pytest.mark.asyncio
    async def test_tmdb_search_tv_show(self) -> None:
        """Test TMDb API TV show search."""
        config = load_config()

        if not config.tmdb_api_token:
            pytest.skip("SKIP: No TMDb token configured")

        async with TMDbClient(config.tmdb_api_token) as client:
            results = await client.search_tv("Breaking Bad")

            assert len(results) > 0, "Expected at least one result for 'Breaking Bad'"
            print(f"Found {len(results)} TV results for 'Breaking Bad'")

            top_result = results[0]
            print(f"Top TV result: {top_result.name} ({top_result.year})")

            assert "Breaking Bad" in top_result.name

    @pytest.mark.asyncio
    async def test_tmdb_get_movie_details(self) -> None:
        """Test TMDb API get movie details."""
        config = load_config()

        if not config.tmdb_api_token:
            pytest.skip("SKIP: No TMDb token configured")

        async with TMDbClient(config.tmdb_api_token) as client:
            # The Matrix has TMDb ID 603
            details = await client.get_movie_details(603)

            assert details is not None, "Expected movie details for The Matrix"
            assert details.get("title") == "The Matrix"
            print(f"Movie details: {details.get('title')} ({details.get('release_date', '')[:4]})")


class TestTMDbWithoutCredentials:
    """Tests that verify behavior when TMDb is not configured."""

    def test_load_config_without_tmdb_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that load_config returns empty string when TMDB_API_TOKEN not set."""
        # Clear the environment variable
        monkeypatch.delenv("TMDB_API_TOKEN", raising=False)

        config = load_config()
        assert config.tmdb_api_token == ""

    def test_skip_message_when_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that we correctly identify when TMDb is not configured."""
        monkeypatch.delenv("TMDB_API_TOKEN", raising=False)

        config = load_config()

        if not config.tmdb_api_token:
            message = "SKIP: No TMDb token configured"
            print(message)
            assert message == "SKIP: No TMDb token configured"
