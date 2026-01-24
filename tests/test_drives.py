"""Tests for the drive detection module."""

from unittest.mock import AsyncMock, patch

import pytest

from dvdtoplex.drives import get_drive_status


class TestGetDriveStatusMakeMKV:
    """Tests for MakeMKV-based get_drive_status function."""

    @pytest.mark.asyncio
    async def test_returns_status_with_disc(self) -> None:
        """Should return DriveStatus with disc info from MakeMKV."""
        with patch("dvdtoplex.drives.check_disc_present") as mock_check:
            mock_check.return_value = (True, "MOVIE_TITLE")

            status = await get_drive_status("0")

            assert status.drive_id == "0"
            assert status.has_disc is True
            assert status.disc_label == "MOVIE_TITLE"
            mock_check.assert_called_once_with("0")

    @pytest.mark.asyncio
    async def test_returns_status_without_disc(self) -> None:
        """Should return DriveStatus without disc."""
        with patch("dvdtoplex.drives.check_disc_present") as mock_check:
            mock_check.return_value = (False, None)

            status = await get_drive_status("1")

            assert status.drive_id == "1"
            assert status.has_disc is False
            assert status.disc_label is None

    @pytest.mark.asyncio
    async def test_handles_device_path(self) -> None:
        """Should handle device path format."""
        with patch("dvdtoplex.drives.check_disc_present") as mock_check:
            mock_check.return_value = (True, "BLURAY_DISC")

            status = await get_drive_status("/dev/disk4")

            assert status.drive_id == "/dev/disk4"
            assert status.has_disc is True
            assert status.disc_label == "BLURAY_DISC"
            mock_check.assert_called_once_with("/dev/disk4")
