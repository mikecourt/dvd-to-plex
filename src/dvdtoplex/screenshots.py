"""Screenshot extraction from video files using ffmpeg."""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default number of screenshots to extract
DEFAULT_SCREENSHOT_COUNT = 4

# Time offsets as percentage of video duration (avoid start/end credits)
DEFAULT_TIME_OFFSETS = [0.15, 0.35, 0.55, 0.75]


async def get_video_duration(video_path: Path) -> float | None:
    """Get the duration of a video file in seconds.

    Args:
        video_path: Path to the video file.

    Returns:
        Duration in seconds, or None if unable to determine.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0 and stdout:
            return float(stdout.decode().strip())
    except Exception as e:
        logger.error(f"Error getting video duration: {e}")

    return None


async def extract_screenshots(
    video_path: Path,
    output_dir: Path,
    count: int = DEFAULT_SCREENSHOT_COUNT,
    time_offsets: list[float] | None = None,
) -> list[Path]:
    """Extract screenshots from a video file.

    Extracts frames at specified time offsets (as percentage of duration).
    Screenshots are saved as JPEG files.

    Args:
        video_path: Path to the video file.
        output_dir: Directory to save screenshots.
        count: Number of screenshots to extract (used if time_offsets not provided).
        time_offsets: List of time offsets as percentage (0.0-1.0) of video duration.
                     If None, uses evenly spaced offsets avoiding first/last 10%.

    Returns:
        List of paths to extracted screenshot files.
    """
    if not video_path.exists():
        logger.error(f"Video file not found: {video_path}")
        return []

    # Get video duration
    duration = await get_video_duration(video_path)
    if duration is None or duration <= 0:
        logger.error(f"Could not determine video duration for {video_path}")
        return []

    # Use provided offsets or calculate evenly spaced ones
    if time_offsets is None:
        if count == DEFAULT_SCREENSHOT_COUNT:
            time_offsets = DEFAULT_TIME_OFFSETS
        else:
            # Generate evenly spaced offsets between 10% and 90% of duration
            time_offsets = [0.1 + (0.8 * i / (count - 1)) for i in range(count)]

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    screenshots: list[Path] = []

    for i, offset in enumerate(time_offsets):
        # Calculate timestamp in seconds
        timestamp = duration * offset

        # Output filename
        output_path = output_dir / f"screenshot_{i+1:02d}.jpg"

        try:
            # Extract frame using ffmpeg
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",  # Overwrite output
                "-ss", str(timestamp),  # Seek to timestamp
                "-i", str(video_path),
                "-vframes", "1",  # Extract one frame
                "-q:v", "2",  # High quality JPEG
                "-vf", "scale='min(1280,iw)':-1",  # Max width 1280, maintain aspect
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0 and output_path.exists():
                screenshots.append(output_path)
                logger.debug(f"Extracted screenshot at {timestamp:.1f}s: {output_path}")
            else:
                logger.warning(
                    f"Failed to extract screenshot at {timestamp:.1f}s: "
                    f"{stderr.decode()[:200]}"
                )

        except Exception as e:
            logger.error(f"Error extracting screenshot at {timestamp:.1f}s: {e}")

    logger.info(
        f"Extracted {len(screenshots)}/{len(time_offsets)} screenshots from {video_path.name}"
    )
    return screenshots


async def extract_screenshots_for_job(
    encode_path: Path,
    job_id: int,
    staging_dir: Path,
) -> list[Path]:
    """Extract screenshots for a specific job.

    Convenience function that creates an appropriate output directory
    and extracts screenshots.

    Args:
        encode_path: Path to the encoded video file.
        job_id: Job ID for directory naming.
        staging_dir: Base staging directory.

    Returns:
        List of paths to extracted screenshot files.
    """
    output_dir = staging_dir / f"job_{job_id}" / "screenshots"
    return await extract_screenshots(encode_path, output_dir)
