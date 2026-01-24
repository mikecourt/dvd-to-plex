"""MakeMKV CLI wrapper for disc info and ripping."""

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class MakeMKVError(Exception):
    """Base exception for MakeMKV errors."""

    pass


class DiscReadError(MakeMKVError):
    """Error reading disc information."""

    def __init__(
        self,
        message: str,
        *,
        device: str,
        details: str | None = None,
    ) -> None:
        """Initialize DiscReadError.

        Args:
            message: Error message.
            device: Device path that caused the error.
            details: Optional additional details about the error.
        """
        super().__init__(message)
        self.device = device
        self.details = details


class RipError(MakeMKVError):
    """Error ripping title from disc."""

    def __init__(
        self,
        message: str,
        *,
        device: str,
        title_index: int,
        details: str | None = None,
    ) -> None:
        """Initialize RipError.

        Args:
            message: Error message.
            device: Device path that caused the error.
            title_index: Index of the title that failed to rip.
            details: Optional additional details about the error.
        """
        super().__init__(message)
        self.device = device
        self.title_index = title_index
        self.details = details


# Path to MakeMKV command line tool
MAKEMKV_PATH = "/Applications/MakeMKV.app/Contents/MacOS/makemkvcon"


@dataclass
class TitleInfo:
    """Information about a title on a disc."""

    index: int
    duration_seconds: int
    size_bytes: int
    filename: str
    chapters: int = 0


def parse_duration(duration_str: str) -> int:
    """Parse duration string to seconds.

    Args:
        duration_str: Duration in format "H:MM:SS" or "MM:SS".

    Returns:
        Duration in seconds.
    """
    parts = duration_str.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + int(seconds)
    return 0


def parse_size(size_str: str) -> int:
    """Parse size string to bytes.

    Args:
        size_str: Size string like "4.7 GB", "700 MB", or "1024" (bytes).

    Returns:
        Size in bytes.
    """
    # Try to match with unit
    match = re.match(r"([\d.]+)\s*(GB|MB|KB|B)", size_str, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        unit = match.group(2).upper()

        multipliers = {
            "B": 1,
            "KB": 1024,
            "MB": 1024 * 1024,
            "GB": 1024 * 1024 * 1024,
        }
        return int(value * multipliers.get(unit, 1))

    # Try to match plain number (no unit = bytes)
    plain_match = re.match(r"^(\d+)$", size_str.strip())
    if plain_match:
        return int(plain_match.group(1))

    return 0


def parse_title_info(output: str) -> list[TitleInfo]:
    """Parse MakeMKV info output to extract title information.

    Args:
        output: Raw output from makemkvcon info command.

    Returns:
        List of TitleInfo objects for each title.
    """
    titles: dict[int, dict[str, str | int]] = {}

    for line in output.splitlines():
        # TINFO lines contain title information
        # Format: TINFO:title_index,attribute_id,code,value
        if not line.startswith("TINFO:"):
            continue

        parts = line[6:].split(",", 3)
        if len(parts) < 4:
            continue

        title_idx = int(parts[0])
        attr_id = int(parts[1])
        value = parts[3].strip('"')

        if title_idx not in titles:
            titles[title_idx] = {
                "index": title_idx,
                "duration": 0,
                "size": 0,
                "filename": "",
                "chapters": 0,
            }

        # Attribute IDs:
        # 8 = chapter count
        # 9 = duration
        # 10 = disk size (bytes)
        # 11 = disk size (formatted, e.g., "4.7 GB")
        # 27 = output filename
        if attr_id == 8:
            titles[title_idx]["chapters"] = int(value)
        elif attr_id == 9:
            titles[title_idx]["duration"] = parse_duration(value)
        elif attr_id == 10:
            titles[title_idx]["size"] = parse_size(value)
        elif attr_id == 11:
            # Use formatted size if byte size is 0
            if titles[title_idx]["size"] == 0:
                titles[title_idx]["size"] = parse_size(value)
        elif attr_id == 27:
            titles[title_idx]["filename"] = value

    result: list[TitleInfo] = []
    for data in titles.values():
        result.append(
            TitleInfo(
                index=int(data["index"]),
                duration_seconds=int(data.get("duration", 0)),
                size_bytes=int(data.get("size", 0)),
                filename=str(data.get("filename", "")),
                chapters=int(data.get("chapters", 0)),
            )
        )

    return sorted(result, key=lambda t: t.index)


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


def _drutil_to_makemkv_id(drive_id: str) -> str:
    """Convert drutil drive ID (1-based) to MakeMKV drive ID (0-based).

    Args:
        drive_id: drutil drive ID (e.g., "1", "2") or device path.

    Returns:
        MakeMKV-compatible drive ID.
    """
    if drive_id.isdigit():
        # drutil uses 1-based, MakeMKV uses 0-based
        return str(int(drive_id) - 1)
    return drive_id


def _extract_makemkv_messages(output: str) -> list[str]:
    """Extract human-readable messages from MakeMKV output.

    Args:
        output: Raw MakeMKV output.

    Returns:
        List of message strings (skipping routine status messages).
    """
    messages = []
    for line in output.splitlines():
        if line.startswith("MSG:"):
            # Format: MSG:code,flags,count,"message","format",...
            parts = line[4:].split(",", 3)
            if len(parts) >= 4:
                # Extract the human-readable message (4th part, quoted)
                msg = parts[3].strip('"').split('","')[0]
                # Skip routine messages
                if not any(skip in msg.lower() for skip in [
                    "started", "opened in os access mode", "operation successfully"
                ]):
                    messages.append(msg)
    return messages


async def get_disc_info(drive_id: str) -> list[TitleInfo]:
    """Get information about all titles on a disc.

    Args:
        drive_id: Device path or drutil drive number (1-based).

    Returns:
        List of TitleInfo objects for each title on the disc.

    Raises:
        DiscReadError: If no titles can be found, with diagnostic details.
    """
    try:
        # Convert drutil ID to MakeMKV ID and format source
        mkv_id = _drutil_to_makemkv_id(drive_id)
        source = f"disc:{mkv_id}" if mkv_id.isdigit() else f"dev:{mkv_id}"

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

        titles = parse_title_info(output)

        if not titles:
            # Extract diagnostic messages from MakeMKV
            messages = _extract_makemkv_messages(output)
            if messages:
                logger.warning(f"MakeMKV messages for {drive_id}: {messages}")
            raise DiscReadError(
                "No titles found on disc",
                device=drive_id,
                details="; ".join(messages) if messages else None,
            )

        return titles
    except DiscReadError:
        raise  # Re-raise DiscReadError as-is
    except Exception as e:
        logger.error(f"Error getting disc info for {drive_id}: {e}")
        raise DiscReadError(
            f"Failed to read disc: {e}",
            device=drive_id,
        )


async def rip_title(
    drive_id: str,
    title_index: int,
    output_dir: Path,
    progress_callback: Callable[[float], None] | None = None,
) -> Path | None:
    """Rip a specific title from a disc.

    Args:
        drive_id: Device path or drive number.
        title_index: Index of the title to rip.
        output_dir: Directory to save the ripped file.
        progress_callback: Optional callback for progress updates (0.0 to 1.0).

    Returns:
        Path to the ripped file, or None if ripping failed.
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Convert drutil ID to MakeMKV ID and format source
        mkv_id = _drutil_to_makemkv_id(drive_id)
        source = f"disc:{mkv_id}" if mkv_id.isdigit() else f"dev:{mkv_id}"

        proc = await asyncio.create_subprocess_exec(
            MAKEMKV_PATH,
            "mkv",
            source,
            str(title_index),
            str(output_dir),
            "-r",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,  # Robot mode outputs to stdout
        )

        # Read output and parse progress
        assert proc.stdout is not None

        # Collect messages from stdout (robot mode uses MSG: lines for errors)
        msg_lines: list[str] = []

        while True:
            line = await proc.stdout.readline()
            if not line:
                break

            text = line.decode("utf-8", errors="replace")

            # Progress lines: PRGV:current,total,max
            if text.startswith("PRGV:") and progress_callback:
                parts = text[5:].strip().split(",")
                if len(parts) >= 3:
                    current = int(parts[0])
                    total = int(parts[2])
                    if total > 0:
                        progress_callback(current / total)
            # Message lines: MSG:code,flags,count,"message",...
            elif text.startswith("MSG:"):
                # Extract the message text (4th field, quoted)
                parts = text[4:].split(",", 3)
                if len(parts) >= 4:
                    msg = parts[3].strip().strip('"').split('","')[0]
                    msg_lines.append(msg)

        await proc.wait()

        if proc.returncode != 0:
            error_detail = "; ".join(msg_lines[-5:]) if msg_lines else "no details"
            logger.error(f"MakeMKV rip failed with return code {proc.returncode}: {error_detail}")
            raise RipError(
                f"MakeMKV failed (exit {proc.returncode}): {error_detail}",
                device=drive_id,
                title_index=title_index,
                details=error_detail,
            )

        # Find the output file
        mkv_files = list(output_dir.glob("*.mkv"))
        if mkv_files:
            return mkv_files[0]

        # No file produced - build error message from MakeMKV output
        error_detail = "; ".join(msg_lines[-10:]) if msg_lines else "No MKV file produced"
        logger.error(f"MakeMKV messages: {error_detail}")
        raise RipError(
            f"Ripping failed: {error_detail}",
            device=drive_id,
            title_index=title_index,
            details=error_detail,
        )

    except RipError:
        raise  # Re-raise RipError as-is
    except Exception as e:
        logger.error(f"Error ripping title {title_index} from {drive_id}: {e}")
        raise RipError(
            f"Ripping error: {e}",
            device=drive_id,
            title_index=title_index,
            details=str(e),
        )
