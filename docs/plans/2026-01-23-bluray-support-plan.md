# Blu-ray Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace drutil-based disc detection with MakeMKV-based detection to support both DVD and Blu-ray discs.

**Architecture:** Replace `drives.py` detection functions to use MakeMKV's `info` command instead of macOS `drutil`. MakeMKV already handles both DVD and Blu-ray, so this unifies detection. Increase poll interval to 15 seconds to accommodate MakeMKV startup time.

**Tech Stack:** Python asyncio, MakeMKV CLI (`makemkvcon`)

---

## Task 1: Update Poll Interval Default

**Files:**
- Modify: `src/dvdtoplex/config.py:32`

**Step 1: Update the default poll interval**

Change line 32 from:
```python
    drive_poll_interval: float = 5.0
```

To:
```python
    drive_poll_interval: float = 15.0
```

**Step 2: Run existing tests to verify no breakage**

Run: `pytest tests/test_config.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add src/dvdtoplex/config.py
git commit -m "chore: increase default poll interval to 15s for MakeMKV detection"
```

---

## Task 2: Add MakeMKV Disc Detection Function

**Files:**
- Modify: `src/dvdtoplex/makemkv.py`
- Create: `tests/test_makemkv.py` (add new test class)

**Step 1: Write the failing test for parsing disc info output**

Add to `tests/test_makemkv.py`:

```python
from dvdtoplex.makemkv import parse_disc_info


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_makemkv.py::TestParseDiscInfo -v`
Expected: FAIL with "cannot import name 'parse_disc_info'"

**Step 3: Implement parse_disc_info function**

Add to `src/dvdtoplex/makemkv.py` after the `parse_title_info` function (around line 196):

```python
def parse_disc_info(output: str) -> tuple[bool, str | None]:
    """Parse MakeMKV info output to detect disc presence and label.

    The DRV line format is: DRV:index,flags,count,disc_type,"media_type","label","device"
    - flags & 2 = disc present
    - flags & 256 = no disc

    Args:
        output: Raw output from makemkvcon info command.

    Returns:
        Tuple of (has_disc, disc_label).
    """
    if not output.strip():
        return False, None

    for line in output.splitlines():
        if not line.startswith("DRV:"):
            continue

        # Parse DRV line: DRV:index,flags,count,type,"media","label","device"
        parts = line[4:].split(",", 6)
        if len(parts) < 7:
            continue

        flags = int(parts[1])
        # flags & 256 = no disc, flags & 2 = disc present
        if flags & 256:
            return False, None
        if flags & 2:
            # Label is the 6th field (index 5), quoted
            label = parts[5].strip('"')
            return True, label if label else None

    return False, None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_makemkv.py::TestParseDiscInfo -v`
Expected: All 5 tests pass

**Step 5: Commit**

```bash
git add src/dvdtoplex/makemkv.py tests/test_makemkv.py
git commit -m "feat: add parse_disc_info for MakeMKV-based disc detection"
```

---

## Task 3: Add Async Disc Detection Function

**Files:**
- Modify: `src/dvdtoplex/makemkv.py`
- Modify: `tests/test_makemkv.py`

**Step 1: Write the failing test for check_disc_present**

Add to `tests/test_makemkv.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from dvdtoplex.makemkv import check_disc_present


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_makemkv.py::TestCheckDiscPresent -v`
Expected: FAIL with "cannot import name 'check_disc_present'"

**Step 3: Implement check_disc_present function**

Add to `src/dvdtoplex/makemkv.py` after `parse_disc_info`:

```python
async def check_disc_present(drive_id: str) -> tuple[bool, str | None]:
    """Check if a disc is present in the specified drive using MakeMKV.

    Args:
        drive_id: Drive ID (0-based index or device path).

    Returns:
        Tuple of (has_disc, disc_label).
    """
    try:
        # Format source for MakeMKV
        source = f"disc:{drive_id}" if drive_id.isdigit() else f"dev:{drive_id}"

        proc = await asyncio.create_subprocess_exec(
            MAKEMKV_PATH,
            "info",
            source,
            "-r",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")

        return parse_disc_info(output)
    except Exception as e:
        logger.error(f"Error checking disc in drive {drive_id}: {e}")
        return False, None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_makemkv.py::TestCheckDiscPresent -v`
Expected: All 3 tests pass

**Step 5: Commit**

```bash
git add src/dvdtoplex/makemkv.py tests/test_makemkv.py
git commit -m "feat: add check_disc_present async function for MakeMKV detection"
```

---

## Task 4: Update drives.py to Use MakeMKV Detection

**Files:**
- Modify: `src/dvdtoplex/drives.py`
- Modify: `tests/test_drives.py`

**Step 1: Write the failing test for new get_drive_status**

Add to `tests/test_drives.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_drives.py::TestGetDriveStatusMakeMKV -v`
Expected: FAIL (tests call the old drutil-based implementation)

**Step 3: Replace get_drive_status implementation**

Replace the contents of `src/dvdtoplex/drives.py` with:

```python
"""DVD/Blu-ray drive detection and control using MakeMKV and drutil."""

import asyncio
import logging
from dataclasses import dataclass

from dvdtoplex.makemkv import check_disc_present

logger = logging.getLogger(__name__)


@dataclass
class DriveStatus:
    """Status of a DVD/Blu-ray drive."""

    drive_id: str
    vendor: str | None
    has_disc: bool
    disc_label: str | None


async def get_drive_status(drive_id: str) -> DriveStatus:
    """Get status of a specific drive using MakeMKV.

    Args:
        drive_id: Drive index (0-based) or device path like '/dev/disk2'.

    Returns:
        DriveStatus with current drive state.
    """
    try:
        has_disc, disc_label = await check_disc_present(drive_id)

        return DriveStatus(
            drive_id=drive_id,
            vendor=None,  # MakeMKV doesn't provide vendor info
            has_disc=has_disc,
            disc_label=disc_label,
        )
    except Exception as e:
        logger.error(f"Error getting drive status for {drive_id}: {e}")
        return DriveStatus(
            drive_id=drive_id,
            vendor=None,
            has_disc=False,
            disc_label=None,
        )


async def eject_drive(drive_id: str) -> bool:
    """Eject a disc from the specified drive.

    Uses drutil for ejecting as it works reliably for both DVD and Blu-ray.

    Args:
        drive_id: Device path or drive number.

    Returns:
        True if eject command succeeded, False otherwise.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "drutil", "eject", "-drive", drive_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception as e:
        logger.error(f"Error ejecting drive {drive_id}: {e}")
        return False
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_drives.py::TestGetDriveStatusMakeMKV -v`
Expected: All 3 tests pass

**Step 5: Commit**

```bash
git add src/dvdtoplex/drives.py tests/test_drives.py
git commit -m "feat: replace drutil with MakeMKV for disc detection"
```

---

## Task 5: Remove Obsolete drutil Code and Tests

**Files:**
- Modify: `tests/test_drives.py`

**Step 1: Remove old drutil parsing tests**

The `TestParseDrutilOutput` class in `tests/test_drives.py` tests code that no longer exists. Delete the entire class (lines 1-82 approximately).

Keep only the imports needed for the new tests:
```python
"""Tests for the drive detection module."""

from unittest.mock import AsyncMock, patch

import pytest

from dvdtoplex.drives import DriveStatus, get_drive_status


class TestGetDriveStatusMakeMKV:
    # ... (the tests from Task 4)
```

**Step 2: Run all drive tests to verify**

Run: `pytest tests/test_drives.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_drives.py
git commit -m "chore: remove obsolete drutil parsing tests"
```

---

## Task 6: Update .env.example Documentation

**Files:**
- Modify: `.env.example` (if exists, otherwise create)

**Step 1: Check if .env.example exists and update**

If `.env.example` exists, ensure the `DRIVE_POLL_INTERVAL` comment reflects the new default:

```bash
# Drive polling interval in seconds (default: 15)
# Increased from 5s to accommodate MakeMKV disc detection startup time
DRIVE_POLL_INTERVAL=15
```

**Step 2: Commit if changes made**

```bash
git add .env.example
git commit -m "docs: update poll interval documentation for MakeMKV detection"
```

---

## Task 7: Run Full Test Suite

**Step 1: Run all tests**

Run: `pytest --ignore=tests/test_pushover_integration.py -v`
Expected: 517+ passed (same baseline as before, minus the obsolete drutil tests)

**Step 2: Verify no regressions**

Check that:
- All makemkv tests pass
- All drives tests pass
- All drive_watcher tests pass
- No new failures introduced

---

## Task 8: Manual Integration Test

**Step 1: Test with actual disc**

1. Insert a DVD in the bottom drive
2. Run the application: `python -m dvdtoplex`
3. Verify the disc is detected in logs
4. Verify a job is created

**Step 2: Test with Blu-ray (if available)**

1. Insert a Blu-ray in the bottom drive
2. Verify the disc is detected
3. Verify ripping starts successfully

**Step 3: Document any issues found**

Note any edge cases or issues for follow-up.

---

## Summary of Changes

| File | Change |
|------|--------|
| `src/dvdtoplex/config.py` | Default poll interval: 5.0 → 15.0 |
| `src/dvdtoplex/makemkv.py` | Add `parse_disc_info()` and `check_disc_present()` |
| `src/dvdtoplex/drives.py` | Replace drutil with MakeMKV-based detection |
| `tests/test_makemkv.py` | Add tests for new detection functions |
| `tests/test_drives.py` | Replace drutil tests with MakeMKV tests |
