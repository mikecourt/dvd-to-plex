"""HandBrake CLI wrapper for encoding."""

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class EncodeError(Exception):
    """Base exception for encoding errors."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        input_path: Path | None = None,
        output_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.input_path = input_path
        self.output_path = output_path


class HandBrakeNotFoundError(EncodeError):
    """HandBrake CLI not found."""

    def __init__(self, message: str, *, path: str) -> None:
        super().__init__(message)
        self.path = path


class InputFileError(EncodeError):
    """Error with input file."""

    def __init__(self, message: str, *, input_path: Path, details: str) -> None:
        super().__init__(message)
        self.input_path = input_path
        self.details = details


class OutputFileError(EncodeError):
    """Error with output file."""

    def __init__(self, message: str, *, output_path: Path, details: str) -> None:
        super().__init__(message)
        self.output_path = output_path
        self.details = details


@dataclass
class EncodeProgress:
    """Progress information for encoding."""

    percent: float
    fps: float | None = None
    eta: str | None = None


def _extract_error_details(stderr_lines: list[str], max_lines: int = 10) -> str:
    """Extract error-related lines from stderr.

    Args:
        stderr_lines: Lines from stderr output.
        max_lines: Maximum number of lines to return.

    Returns:
        Filtered error details as a string.
    """
    if not stderr_lines:
        return "No error details available"

    error_keywords = ["error", "fail", "invalid", "cannot", "unable", "exception"]
    error_lines = []

    for line in stderr_lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in error_keywords):
            error_lines.append(line)

    # If no error keywords found, fall back to last N lines
    if not error_lines:
        return "\n".join(stderr_lines[-max_lines:])

    return "\n".join(error_lines[:max_lines])


def parse_progress_line(line: str) -> EncodeProgress | None:
    """Parse a HandBrake progress line.

    Args:
        line: A line from HandBrake output.

    Returns:
        EncodeProgress if line contains progress info, None otherwise.
    """
    # Progress lines look like: "Encoding: task 1 of 1, 45.67 %"
    # Or: "Encoding: task 1 of 1, 45.67 % (30.5 fps, avg 29.8 fps, ETA 00h05m12s)"
    if "Encoding:" not in line:
        return None

    match = re.search(r"(\d+\.?\d*)\s*%", line)
    if not match:
        return None

    percent = float(match.group(1))

    # Try to extract FPS
    fps: float | None = None
    fps_match = re.search(r"\((\d+\.?\d*)\s*fps", line)
    if fps_match:
        fps = float(fps_match.group(1))

    # Try to extract ETA as string
    eta: str | None = None
    eta_match = re.search(r"ETA\s+(\d+h\d+m\d+s)", line)
    if eta_match:
        eta = eta_match.group(1)

    return EncodeProgress(percent=percent, fps=fps, eta=eta)


# Default HandBrakeCLI command (relies on PATH)
DEFAULT_HANDBRAKE_PATH = "HandBrakeCLI"


def build_encode_command(
    input_path: Path,
    output_path: Path,
    handbrake_cli: str = DEFAULT_HANDBRAKE_PATH,
) -> list[str]:
    """Build HandBrakeCLI command with encoding settings.

    Settings (DVD_Archive_RF16_x264 preset):
    - x264 encoder, slow preset, film tune
    - Quality RF 16
    - High profile, level 4.0
    - AAC stereo 192kbps
    - Decomb deinterlacing
    - Chapter markers
    - CFR framerate

    Args:
        input_path: Path to input MKV file.
        output_path: Path for output file.
        handbrake_cli: Path to HandBrakeCLI executable.

    Returns:
        Command as list of arguments.
    """
    return [
        handbrake_cli,
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        # Video settings
        "-e",
        "x264",
        "-q",
        "16",
        "--encoder-profile",
        "high",
        "--encoder-level",
        "4.0",
        "--encoder-preset",
        "slow",
        "--encoder-tune",
        "film",
        # Framerate
        "--cfr",
        # Deinterlacing
        "--decomb",
        # Audio settings: AAC stereo 192kbps
        "-a",
        "1",
        "-E",
        "av_aac",
        "-B",
        "192",
        "--mixdown",
        "stereo",
        "-R",
        "auto",
        # Chapter markers
        "--markers",
        # Picture settings
        "--auto-anamorphic",
        "--modulus",
        "2",
        # Container
        "-f",
        "mkv",
    ]


async def encode_file(
    input_path: Path,
    output_path: Path,
    progress_callback: Callable[[EncodeProgress], None] | None = None,
    handbrake_cli: str = DEFAULT_HANDBRAKE_PATH,
) -> None:
    """Encode a file using HandBrake.

    Args:
        input_path: Path to input MKV file.
        output_path: Path for output file.
        progress_callback: Optional callback for progress updates.
        handbrake_cli: Path to HandBrakeCLI executable.

    Raises:
        InputFileError: If input file doesn't exist or is not a file.
        HandBrakeNotFoundError: If HandBrakeCLI is not found.
        EncodeError: If encoding fails with non-zero exit code.
        OutputFileError: If output file is not created or is empty.
    """
    # Validate input file
    if not input_path.exists():
        raise InputFileError(
            f"Input file does not exist: {input_path}",
            input_path=input_path,
            details="Input file does not exist",
        )
    if not input_path.is_file():
        raise InputFileError(
            f"Input path is not a file: {input_path}",
            input_path=input_path,
            details="Input path is not a file",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_encode_command(input_path, output_path, handbrake_cli)

    stderr_lines: list[str] = []

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,  # Don't capture stdout - prevents buffer deadlock
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise HandBrakeNotFoundError(
            f"HandBrakeCLI not found: {handbrake_cli}",
            path=handbrake_cli,
        )

    # Read stderr for progress and error messages
    assert proc.stderr is not None
    while True:
        line = await proc.stderr.readline()
        if not line:
            break

        text = line.decode("utf-8", errors="replace").rstrip()
        stderr_lines.append(text)

        # Parse and report progress
        if progress_callback and "Encoding:" in text:
            progress = parse_progress_line(text)
            if progress is not None:
                progress_callback(progress)

    await proc.wait()

    if proc.returncode != 0:
        logger.error(f"HandBrake encoding failed with return code {proc.returncode}")
        raise EncodeError(
            f"Encoding failed with exit code {proc.returncode}",
            exit_code=proc.returncode,
            input_path=input_path,
            output_path=output_path,
        )

    if not output_path.exists():
        logger.error("Output file not created after encoding")
        raise OutputFileError(
            f"Output file was not created: {output_path}",
            output_path=output_path,
            details="Output file was not created",
        )

    if output_path.stat().st_size == 0:
        logger.error("Output file is empty after encoding")
        raise OutputFileError(
            f"Output file is empty: {output_path}",
            output_path=output_path,
            details="Output file is empty",
        )
