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
