"""TMDb API client for content identification."""

import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

TMDB_API_BASE = "https://api.themoviedb.org/3"


@dataclass
class MovieMatch:
    """A movie search result from TMDb."""

    tmdb_id: int
    title: str
    year: int | None
    overview: str
    poster_path: str | None
    popularity: float


@dataclass
class TVMatch:
    """A TV show search result from TMDb."""

    tmdb_id: int
    name: str
    year: int | None
    overview: str
    poster_path: str | None
    popularity: float


@dataclass
class MovieDetails:
    """Detailed movie information from TMDb."""

    tmdb_id: int
    title: str
    year: int | None
    overview: str
    poster_path: str | None
    popularity: float
    runtime: int | None
    genres: list[str]
    tagline: str


@dataclass
class TVSeasonDetails:
    """TV season details from TMDb."""

    tmdb_id: int
    show_name: str
    season_number: int
    name: str
    overview: str
    poster_path: str | None
    air_date: str | None
    episodes: list[dict[str, object]]


def clean_disc_label(label: str) -> str:
    """Clean a disc label for better search matching.

    Removes common patterns like DISC_1, DVD, WIDESCREEN, WS, region codes, etc.

    Args:
        label: Raw disc label.

    Returns:
        Cleaned label suitable for searching (lowercase).
    """
    # Work with the label
    cleaned = label

    # Remove common disc patterns (case-insensitive)
    # Order matters: more specific patterns first, and patterns that should only
    # match at boundaries use \b or _ anchors
    patterns = [
        r"_*DISC_*\d+",
        r"_*DISC\d+",
        r"^DVD_",  # DVD at start
        r"_DVD$",  # DVD at end
        r"_DVD_",  # DVD in middle
        r"_*WIDESCREEN",
        r"(?:^|_)WS(?:_|$)",  # WS only at boundaries
        r"_*FULLSCREEN",
        r"(?:^|_|\s)FS(?:_|$|\s|$)",  # FS only at boundaries (underscore or space)
        r"_*SPECIAL_*EDITION",
        r"(?:^|_)SE(?:_|$)",  # SE only at boundaries
        r"_*DIRECTORS_*CUT",
        r"(?:^|_)DC(?:_|$)",  # DC only at boundaries
        r"_*UNRATED",
        r"_*EXTENDED",
        r"_*THEATRICAL",
        r"_*COLLECTORS_*EDITION",
        r"(?:^|_)CE(?:_|$)",  # CE only at boundaries
        r"_*PLATINUM_*EDITION",
        r"_*ANNIVERSARY_*EDITION",
        r"_*\d+TH_*ANNIVERSARY",
        r"_*BLURAY",
        r"_*BLU_*RAY",
        r"(?:^|_)HD(?:_|$)",  # HD only at boundaries
        r"(?:^|_)4K(?:_|$)",  # 4K only at boundaries
        r"_*D\d+$",  # D1, D2 at end
        r"_R\d+$",  # Region codes like _R1 at end
        r"_REGION_*\d+",  # Region codes like _REGION_2
        # Aspect ratio markers
        r"_*16X9",
        r"_*4X3",
        r"_*ANAMORPHIC",
        # Region/format markers
        r"_*US_*DES",  # US Destination/Design
        r"_*UK_*DES",
        r"(?:^|_)PS(?:_|$)",  # Pan & Scan or PlayStation
        r"(?:^|_)DES(?:_|$)",  # Destination marker
        r"_*NTSC",
        r"_*PAL",
        # Version markers
        r"_*V\d+$",  # V1, V2 at end
        r"_*VERSION_*\d+",
        # Additional edition markers
        r"_*DELUXE",
        r"_*ULTIMATE",
        r"_*REMASTERED",
        r"_*RESTORED",
        # Studio/distribution markers at end
        r"_+[A-Z]\d*$",  # Single letter + optional number at end (A1, B1, etc.)
    ]

    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    # Replace underscores with spaces
    cleaned = cleaned.replace("_", " ")

    # Remove multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Strip and convert to lowercase
    return cleaned.strip().lower()


class TMDbClient:
    """Client for TMDb API."""

    def __init__(self, api_token: str) -> None:
        """Initialize TMDb client.

        Args:
            api_token: TMDb API read access token.
        """
        self.api_token = api_token
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TMDbClient":
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=TMDB_API_BASE,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client, raising if not in context."""
        if self._client is None:
            raise RuntimeError("TMDbClient must be used as async context manager")
        return self._client

    def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client for testing.

        Returns:
            The HTTP client instance.
        """
        return self.client

    def _extract_year(self, date_str: str | None) -> int | None:
        """Extract year from a date string.

        Args:
            date_str: Date string in YYYY-MM-DD format or None.

        Returns:
            Year as integer or None if invalid.
        """
        if not date_str or len(date_str) < 4:
            return None
        try:
            return int(date_str[:4])
        except ValueError:
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search_movie(
        self, query: str, year: int | None = None
    ) -> list[MovieMatch]:
        """Search for movies.

        Args:
            query: Search query.
            year: Optional year to filter results.

        Returns:
            List of MovieMatch results (up to 10).
        """
        try:
            params: dict[str, str | int] = {"query": query}
            if year:
                params["year"] = year

            http_client = self._get_client()
            response = await http_client.get("/search/movie", params=params)
            response.raise_for_status()
            data = response.json()

            results: list[MovieMatch] = []
            for item in data.get("results", [])[:10]:
                year_val = self._extract_year(item.get("release_date"))

                results.append(
                    MovieMatch(
                        tmdb_id=item["id"],
                        title=item.get("title", ""),
                        year=year_val,
                        overview=item.get("overview", ""),
                        poster_path=item.get("poster_path"),
                        popularity=item.get("popularity", 0.0),
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Error searching movies for '{query}': {e}")
            return []

    async def search_tv(self, query: str, year: int | None = None) -> list[TVMatch]:
        """Search for TV shows.

        Args:
            query: Search query.
            year: Optional first air year to filter results.

        Returns:
            List of TVMatch results (up to 10).
        """
        try:
            params: dict[str, str | int] = {"query": query}
            if year:
                params["first_air_date_year"] = year

            http_client = self._get_client()
            response = await http_client.get("/search/tv", params=params)
            response.raise_for_status()
            data = response.json()

            results: list[TVMatch] = []
            for item in data.get("results", [])[:10]:
                year_val = self._extract_year(item.get("first_air_date"))

                results.append(
                    TVMatch(
                        tmdb_id=item["id"],
                        name=item.get("name", ""),
                        year=year_val,
                        overview=item.get("overview", ""),
                        poster_path=item.get("poster_path"),
                        popularity=item.get("popularity", 0.0),
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Error searching TV for '{query}': {e}")
            return []

    async def get_movie_details(self, tmdb_id: int) -> MovieDetails | None:
        """Get detailed movie information.

        Args:
            tmdb_id: TMDb movie ID.

        Returns:
            MovieDetails object or None if not found.
        """
        try:
            http_client = self._get_client()
            response = await http_client.get(f"/movie/{tmdb_id}")
            response.raise_for_status()
            data = response.json()

            year_val = self._extract_year(data.get("release_date"))
            genres = [g["name"] for g in data.get("genres", [])]

            return MovieDetails(
                tmdb_id=data["id"],
                title=data.get("title", ""),
                year=year_val,
                overview=data.get("overview", ""),
                poster_path=data.get("poster_path"),
                popularity=data.get("popularity", 0.0),
                runtime=data.get("runtime"),
                genres=genres,
                tagline=data.get("tagline", ""),
            )
        except Exception as e:
            logger.error(f"Error getting movie details for {tmdb_id}: {e}")
            return None

    async def get_tv_season(
        self,
        tmdb_id: int,
        season_number: int,
    ) -> TVSeasonDetails | None:
        """Get TV season information.

        Args:
            tmdb_id: TMDb TV show ID.
            season_number: Season number.

        Returns:
            TVSeasonDetails object or None if not found.
        """
        try:
            http_client = self._get_client()

            # First get the show name
            show_response = await http_client.get(f"/tv/{tmdb_id}")
            show_response.raise_for_status()
            show_data = show_response.json()
            show_name = show_data.get("name", "")

            # Then get the season details
            season_response = await http_client.get(
                f"/tv/{tmdb_id}/season/{season_number}"
            )
            season_response.raise_for_status()
            data = season_response.json()

            return TVSeasonDetails(
                tmdb_id=tmdb_id,
                show_name=show_name,
                season_number=season_number,
                name=data.get("name", ""),
                overview=data.get("overview", ""),
                poster_path=data.get("poster_path"),
                air_date=data.get("air_date"),
                episodes=data.get("episodes", []),
            )
        except Exception as e:
            logger.error(f"Error getting TV season {season_number} for {tmdb_id}: {e}")
            return None
