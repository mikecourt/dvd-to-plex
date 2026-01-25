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
