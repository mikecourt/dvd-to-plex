"""DVD/Blu-ray drive detection and control using drutil and diskutil."""

import asyncio
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DriveStatus:
    """Status of a DVD/Blu-ray drive."""

    drive_id: str
    vendor: str | None
    has_disc: bool
    disc_label: str | None


async def get_drive_status(drive_id: str) -> DriveStatus:
    """Get status of a specific drive using drutil and diskutil.

    Uses native macOS tools instead of MakeMKV for faster, non-blocking detection.

    Args:
        drive_id: Drive number (1-based, as used by drutil).

    Returns:
        DriveStatus with current drive state.
    """
    try:
        # Use drutil to check disc presence and get device path
        proc = await asyncio.create_subprocess_exec(
            "drutil", "status", "-drive", drive_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        output = stdout.decode("utf-8", errors="replace")

        # Check if media is inserted
        if "No Media Inserted" in output or "Type:" not in output:
            return DriveStatus(
                drive_id=drive_id,
                vendor=None,
                has_disc=False,
                disc_label=None,
            )

        # Extract device path (e.g., /dev/disk4)
        device_match = re.search(r"Name:\s*(/dev/disk\d+)", output)
        if not device_match:
            return DriveStatus(
                drive_id=drive_id,
                vendor=None,
                has_disc=True,
                disc_label=None,
            )

        device_path = device_match.group(1)

        # Use diskutil to get volume name (disc label)
        proc2 = await asyncio.create_subprocess_exec(
            "diskutil", "info", device_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=5.0)
        output2 = stdout2.decode("utf-8", errors="replace")

        # Extract volume name
        volume_match = re.search(r"Volume Name:\s*(.+)", output2)
        disc_label = volume_match.group(1).strip() if volume_match else None

        return DriveStatus(
            drive_id=drive_id,
            vendor=None,
            has_disc=True,
            disc_label=disc_label,
        )

    except asyncio.TimeoutError:
        logger.warning(f"Timeout checking drive {drive_id}")
        return DriveStatus(
            drive_id=drive_id,
            vendor=None,
            has_disc=False,
            disc_label=None,
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
