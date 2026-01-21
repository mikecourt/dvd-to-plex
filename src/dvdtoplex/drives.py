"""DVD drive detection and control using macOS drutil."""

import asyncio
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DriveStatus:
    """Status of a DVD drive."""

    drive_id: str
    vendor: str | None
    has_disc: bool
    disc_label: str | None


def parse_drutil_output(output: str) -> tuple[str, bool, str | None]:
    """Parse drutil status output.

    Args:
        output: Raw output from drutil status command.

    Returns:
        Tuple of (vendor, has_disc, disc_label).
    """
    # Handle empty output edge case
    if not output.strip():
        return "", False, None

    vendor: str = ""
    has_disc = False
    disc_label: str | None = None

    # Parse vendor from Vendor line
    vendor_match = re.search(r"Vendor:\s+(.+)", output)
    if vendor_match:
        vendor = vendor_match.group(1).strip()

    # Check for "No Media Inserted"
    if "No Media Inserted" in output:
        return vendor, False, None

    # Check for disc presence - look for "Media" lines
    if "Media" in output and "No Media" not in output:
        has_disc = True

    # Parse disc label from Name line
    name_match = re.search(r"Name:\s+(.+)", output)
    if name_match:
        disc_label = name_match.group(1).strip()
        has_disc = True

    return vendor, has_disc, disc_label


async def _get_volume_name(device_path: str) -> str | None:
    """Get the volume name from a device path using diskutil.

    Args:
        device_path: Device path like '/dev/disk4'.

    Returns:
        Volume name or None if not found.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "diskutil", "info", device_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")

        # Look for Volume Name line
        match = re.search(r"Volume Name:\s+(.+)", output)
        if match:
            return match.group(1).strip()
        return None
    except Exception:
        return None


async def get_drive_status(drive_id: str) -> DriveStatus:
    """Get status of a specific DVD drive.

    Args:
        drive_id: Device path like '/dev/disk2'.

    Returns:
        DriveStatus with current drive state.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "drutil", "status", "-drive", drive_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        vendor, has_disc, disc_label = parse_drutil_output(output)

        # If we have a disc and the label looks like a device path, get the real volume name
        if has_disc and disc_label and disc_label.startswith("/dev/"):
            volume_name = await _get_volume_name(disc_label)
            if volume_name:
                disc_label = volume_name

        return DriveStatus(
            drive_id=drive_id,
            vendor=vendor,
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


async def list_dvd_drives() -> list[str]:
    """List all DVD drives on the system.

    Returns:
        List of drive device paths.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "drutil", "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")

        drives: list[str] = []
        for line in output.splitlines():
            # Look for lines with device paths
            match = re.search(r"(/dev/disk\d+)", line)
            if match:
                drives.append(match.group(1))

        # Also check for drive indices (drutil uses 1-based indices)
        for i in range(1, 10):  # Check up to 9 drives
            if f"Drive {i}:" in output:
                drives.append(str(i))

        return drives
    except Exception as e:
        logger.error(f"Error listing DVD drives: {e}")
        return []


async def eject_drive(drive_id: str) -> bool:
    """Eject a disc from the specified drive.

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
