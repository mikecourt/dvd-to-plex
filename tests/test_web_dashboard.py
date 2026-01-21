"""Tests for dashboard functionality."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestFormatFileSize:
    """Tests for format_file_size helper."""

    def test_format_bytes(self):
        """Test formatting small sizes in bytes."""
        from dvdtoplex.web.app import format_file_size

        assert format_file_size(0) == "0 B"
        assert format_file_size(500) == "500 B"
        assert format_file_size(1023) == "1023 B"

    def test_format_kilobytes(self):
        """Test formatting kilobyte sizes."""
        from dvdtoplex.web.app import format_file_size

        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(1024 * 1023) == "1023.0 KB"

    def test_format_megabytes(self):
        """Test formatting megabyte sizes."""
        from dvdtoplex.web.app import format_file_size

        assert format_file_size(1024 * 1024) == "1.0 MB"
        assert format_file_size(1024 * 1024 * 500) == "500.0 MB"

    def test_format_gigabytes(self):
        """Test formatting gigabyte sizes."""
        from dvdtoplex.web.app import format_file_size

        assert format_file_size(1024 * 1024 * 1024) == "1.00 GB"
        assert format_file_size(int(1024 * 1024 * 1024 * 2.5)) == "2.50 GB"


class TestGetJobFileSize:
    """Tests for get_job_file_size helper."""

    def test_returns_none_for_non_ripping_status(self):
        """Test returns None for statuses other than ripping/encoding."""
        from dvdtoplex.web.app import get_job_file_size
        from unittest.mock import MagicMock

        mock_config = MagicMock()
        mock_config.staging_dir = Path("/tmp/staging")
        mock_config.encoding_dir = Path("/tmp/encoding")

        assert get_job_file_size(1, "review", mock_config) is None
        assert get_job_file_size(1, "complete", mock_config) is None
        assert get_job_file_size(1, "pending", mock_config) is None

    def test_returns_none_when_directory_missing(self):
        """Test returns None when job directory doesn't exist."""
        from dvdtoplex.web.app import get_job_file_size
        from unittest.mock import MagicMock

        with TemporaryDirectory() as tmpdir:
            mock_config = MagicMock()
            mock_config.staging_dir = Path(tmpdir) / "staging"
            mock_config.encoding_dir = Path(tmpdir) / "encoding"

            # Directories don't exist
            assert get_job_file_size(1, "ripping", mock_config) is None
            assert get_job_file_size(1, "encoding", mock_config) is None

    def test_returns_size_for_ripping_job(self):
        """Test returns file size for ripping job with MKV files."""
        from dvdtoplex.web.app import get_job_file_size
        from unittest.mock import MagicMock

        with TemporaryDirectory() as tmpdir:
            mock_config = MagicMock()
            mock_config.staging_dir = Path(tmpdir)
            mock_config.encoding_dir = Path(tmpdir) / "encoding"

            # Create job directory with MKV file
            job_dir = Path(tmpdir) / "job_1"
            job_dir.mkdir()
            mkv_file = job_dir / "movie.mkv"
            mkv_file.write_bytes(b"x" * 1024 * 1024)  # 1 MB

            result = get_job_file_size(1, "ripping", mock_config)
            assert result == "1.0 MB"

    def test_returns_size_for_encoding_job(self):
        """Test returns file size for encoding job with MKV files."""
        from dvdtoplex.web.app import get_job_file_size
        from unittest.mock import MagicMock

        with TemporaryDirectory() as tmpdir:
            mock_config = MagicMock()
            mock_config.staging_dir = Path(tmpdir) / "staging"
            mock_config.encoding_dir = Path(tmpdir)

            # Create job directory with MKV file
            job_dir = Path(tmpdir) / "job_1"
            job_dir.mkdir()
            mkv_file = job_dir / "encoded.mkv"
            mkv_file.write_bytes(b"x" * 1024 * 1024 * 2)  # 2 MB

            result = get_job_file_size(1, "encoding", mock_config)
            assert result == "2.0 MB"

    def test_sums_multiple_mkv_files(self):
        """Test sums size of multiple MKV files in directory."""
        from dvdtoplex.web.app import get_job_file_size
        from unittest.mock import MagicMock

        with TemporaryDirectory() as tmpdir:
            mock_config = MagicMock()
            mock_config.staging_dir = Path(tmpdir)
            mock_config.encoding_dir = Path(tmpdir) / "encoding"

            # Create job directory with multiple MKV files
            job_dir = Path(tmpdir) / "job_1"
            job_dir.mkdir()
            (job_dir / "title1.mkv").write_bytes(b"x" * 1024 * 1024)  # 1 MB
            (job_dir / "title2.mkv").write_bytes(b"x" * 1024 * 1024)  # 1 MB

            result = get_job_file_size(1, "ripping", mock_config)
            assert result == "2.0 MB"
