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
