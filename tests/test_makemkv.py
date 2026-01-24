"""Tests for the MakeMKV wrapper."""

from unittest.mock import AsyncMock, patch

import pytest

from dvdtoplex.makemkv import (
    check_disc_present,
    DiscReadError,
    MakeMKVError,
    RipError,
    parse_disc_info,
    parse_duration,
    parse_size,
    parse_title_info,
)


class TestParseDuration:
    """Tests for parse_duration function."""

    def test_hours_minutes_seconds(self) -> None:
        """Should parse H:MM:SS format."""
        assert parse_duration("1:30:45") == 1 * 3600 + 30 * 60 + 45

    def test_minutes_seconds(self) -> None:
        """Should parse MM:SS format."""
        assert parse_duration("45:30") == 45 * 60 + 30

    def test_zero_duration(self) -> None:
        """Should handle zero duration."""
        assert parse_duration("0:00:00") == 0

    def test_long_movie(self) -> None:
        """Should handle long durations."""
        assert parse_duration("2:45:30") == 2 * 3600 + 45 * 60 + 30


class TestParseSize:
    """Tests for parse_size function."""

    def test_gigabytes(self) -> None:
        """Should parse GB sizes."""
        assert parse_size("4.7 GB") == int(4.7 * 1024**3)

    def test_megabytes(self) -> None:
        """Should parse MB sizes."""
        assert parse_size("500 MB") == 500 * 1024**2

    def test_kilobytes(self) -> None:
        """Should parse KB sizes."""
        assert parse_size("1024 KB") == 1024 * 1024

    def test_bytes(self) -> None:
        """Should parse byte sizes."""
        assert parse_size("1024 B") == 1024

    def test_no_unit(self) -> None:
        """Should treat no unit as bytes."""
        assert parse_size("1024") == 1024

    def test_invalid_format(self) -> None:
        """Should return 0 for invalid format."""
        assert parse_size("invalid") == 0


class TestParseTitleInfo:
    """Tests for parse_title_info function."""

    def test_parse_single_title(self) -> None:
        """Should parse a single title."""
        output = '''TINFO:0,8,0,"10"
TINFO:0,9,0,"1:45:30"
TINFO:0,10,0,"5000000000"
TINFO:0,27,0,"title00.mkv"
'''
        titles = parse_title_info(output)

        assert len(titles) == 1
        assert titles[0].index == 0
        assert titles[0].duration_seconds == 1 * 3600 + 45 * 60 + 30
        assert titles[0].size_bytes == 5000000000
        assert titles[0].filename == "title00.mkv"
        assert titles[0].chapters == 10

    def test_parse_multiple_titles(self) -> None:
        """Should parse multiple titles."""
        output = '''TINFO:0,9,0,"1:30:00"
TINFO:0,10,0,"4000000000"
TINFO:0,27,0,"title00.mkv"
TINFO:1,9,0,"0:05:00"
TINFO:1,10,0,"100000000"
TINFO:1,27,0,"title01.mkv"
TINFO:2,9,0,"2:00:00"
TINFO:2,10,0,"6000000000"
TINFO:2,27,0,"title02.mkv"
'''
        titles = parse_title_info(output)

        assert len(titles) == 3
        assert titles[0].index == 0
        assert titles[1].index == 1
        assert titles[2].index == 2
        assert titles[2].duration_seconds == 2 * 3600

    def test_parse_empty_output(self) -> None:
        """Should return empty list for empty output."""
        titles = parse_title_info("")
        assert len(titles) == 0

    def test_parse_with_formatted_size(self) -> None:
        """Should parse formatted size if byte size is 0."""
        output = '''TINFO:0,9,0,"1:30:00"
TINFO:0,11,0,"4.7 GB"
TINFO:0,27,0,"title00.mkv"
'''
        titles = parse_title_info(output)

        assert len(titles) == 1
        assert titles[0].size_bytes == int(4.7 * 1024**3)

    def test_ignores_non_tinfo_lines(self) -> None:
        """Should ignore non-TINFO lines."""
        output = '''MSG:0,0,0,"Opening disc..."
PRGT:0,0,"Analyzing disc..."
TINFO:0,9,0,"1:30:00"
TINFO:0,10,0,"4000000000"
TINFO:0,27,0,"title00.mkv"
MSG:0,0,0,"Done"
'''
        titles = parse_title_info(output)

        assert len(titles) == 1
        assert titles[0].index == 0


class TestMakeMKVErrors:
    """Tests for MakeMKV exception classes."""

    def test_disc_read_error_inheritance(self) -> None:
        """DiscReadError should inherit from MakeMKVError."""
        error = DiscReadError("Test error", device="/dev/disk2")
        assert isinstance(error, MakeMKVError)
        assert isinstance(error, Exception)

    def test_disc_read_error_attributes(self) -> None:
        """DiscReadError should store device and details."""
        error = DiscReadError(
            "Failed to read",
            device="/dev/disk2",
            details="Disc is scratched",
        )
        assert str(error) == "Failed to read"
        assert error.device == "/dev/disk2"
        assert error.details == "Disc is scratched"

    def test_disc_read_error_without_details(self) -> None:
        """DiscReadError should work without details."""
        error = DiscReadError("No disc", device="/dev/disk3")
        assert error.details is None
        assert error.device == "/dev/disk3"

    def test_rip_error_inheritance(self) -> None:
        """RipError should inherit from MakeMKVError."""
        error = RipError("Test error", device="/dev/disk2", title_index=0)
        assert isinstance(error, MakeMKVError)
        assert isinstance(error, Exception)

    def test_rip_error_attributes(self) -> None:
        """RipError should store device, title_index, and details."""
        error = RipError(
            "Rip failed",
            device="/dev/disk2",
            title_index=3,
            details="Read error at sector 12345",
        )
        assert str(error) == "Rip failed"
        assert error.device == "/dev/disk2"
        assert error.title_index == 3
        assert error.details == "Read error at sector 12345"

    def test_rip_error_without_details(self) -> None:
        """RipError should work without details."""
        error = RipError("No output", device="/dev/disk3", title_index=0)
        assert error.details is None
        assert error.title_index == 0


class TestParseDiscInfo:
    """Tests for parse_disc_info function."""

    def test_parse_disc_present_with_label(self) -> None:
        """Should detect disc with label from MakeMKV output."""
        output = '''DRV:0,2,999,1,"DVD+R DL","MOVIE_TITLE","/dev/disk4"
TINFO:0,9,0,"1:45:30"
'''
        has_disc, disc_label = parse_disc_info(output)

        assert has_disc is True
        assert disc_label == "MOVIE_TITLE"

    def test_parse_no_disc(self) -> None:
        """Should detect when no disc is present."""
        output = '''DRV:0,256,999,0,"","",""
'''
        has_disc, disc_label = parse_disc_info(output)

        assert has_disc is False
        assert disc_label is None

    def test_parse_disc_without_label(self) -> None:
        """Should handle disc present but no label."""
        output = '''DRV:0,2,999,1,"BD-ROM","","/dev/disk4"
TINFO:0,9,0,"2:00:00"
'''
        has_disc, disc_label = parse_disc_info(output)

        assert has_disc is True
        assert disc_label is None

    def test_parse_empty_output(self) -> None:
        """Should handle empty output."""
        has_disc, disc_label = parse_disc_info("")

        assert has_disc is False
        assert disc_label is None

    def test_parse_bluray_disc(self) -> None:
        """Should detect Blu-ray disc with label."""
        output = '''DRV:0,2,999,12,"BD-ROM","BLURAY_MOVIE","/dev/disk4"
TINFO:0,9,0,"2:30:00"
'''
        has_disc, disc_label = parse_disc_info(output)

        assert has_disc is True
        assert disc_label == "BLURAY_MOVIE"


class TestCheckDiscPresent:
    """Tests for check_disc_present async function."""

    @pytest.mark.asyncio
    async def test_returns_status_when_disc_present(self) -> None:
        """Should return has_disc=True and label when disc is present."""
        mock_output = '''DRV:0,2,999,1,"DVD+R DL","MOVIE_TITLE","/dev/disk4"
'''
        with patch("dvdtoplex.makemkv.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (mock_output.encode(), b"")
            mock_exec.return_value = mock_proc

            has_disc, label = await check_disc_present("0")

            assert has_disc is True
            assert label == "MOVIE_TITLE"

    @pytest.mark.asyncio
    async def test_returns_false_when_no_disc(self) -> None:
        """Should return has_disc=False when no disc is present."""
        mock_output = '''DRV:0,256,999,0,"","",""
'''
        with patch("dvdtoplex.makemkv.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (mock_output.encode(), b"")
            mock_exec.return_value = mock_proc

            has_disc, label = await check_disc_present("0")

            assert has_disc is False
            assert label is None

    @pytest.mark.asyncio
    async def test_handles_exception(self) -> None:
        """Should return False on error."""
        with patch("dvdtoplex.makemkv.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = Exception("Process failed")

            has_disc, label = await check_disc_present("0")

            assert has_disc is False
            assert label is None
