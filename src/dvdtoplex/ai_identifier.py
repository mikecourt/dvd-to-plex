"""AI-powered content identification using Claude."""

import base64
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


@dataclass
class AIIdentificationResult:
    """Result from AI identification."""

    title: str | None
    year: int | None
    confidence: float
    reasoning: str
    is_movie: bool  # True for movie, False for TV


def _load_image_as_base64(image_path: Path) -> tuple[str, str] | None:
    """Load an image file and encode as base64.

    Args:
        image_path: Path to the image file.

    Returns:
        Tuple of (base64_data, media_type) or None if failed.
    """
    try:
        with open(image_path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")

        # Determine media type from extension
        suffix = image_path.suffix.lower()
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_types.get(suffix, "image/jpeg")

        return (data, media_type)
    except Exception as e:
        logger.error(f"Failed to load image {image_path}: {e}")
        return None


async def identify_with_ai(
    disc_label: str,
    screenshot_paths: list[Path],
    api_key: str,
) -> AIIdentificationResult | None:
    """Use Claude AI to identify content from screenshots.

    Args:
        disc_label: The disc label (cleaned or raw).
        screenshot_paths: Paths to screenshot images from the video.
        api_key: Anthropic API key.

    Returns:
        AIIdentificationResult or None if identification failed.
    """
    if not api_key:
        logger.warning("No Anthropic API key configured for AI identification")
        return None

    if not screenshot_paths:
        logger.warning("No screenshots provided for AI identification")
        return None

    # Load images
    images: list[tuple[str, str]] = []
    for path in screenshot_paths[:4]:  # Max 4 images
        result = _load_image_as_base64(path)
        if result:
            images.append(result)

    if not images:
        logger.error("Failed to load any screenshots for AI identification")
        return None

    # Build the message content
    content: list[dict] = []

    # Add images
    for base64_data, media_type in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64_data,
            }
        })

    # Add the prompt
    content.append({
        "type": "text",
        "text": f"""I need help identifying a movie or TV show from these screenshots.

The disc label was: "{disc_label}"

Based on the screenshots and disc label, please identify this content. Look for:
- Visual style, cinematography, and production quality
- Any recognizable actors, settings, or scenes
- Genre indicators (animation style, live action, period piece, etc.)
- Any visible text, titles, or credits

Please respond in this exact format:
TITLE: [exact title of the movie or TV show]
YEAR: [release year, or "unknown" if unsure]
TYPE: [MOVIE or TV]
CONFIDENCE: [HIGH, MEDIUM, or LOW]
REASONING: [brief explanation of how you identified it]

If you cannot identify the content with reasonable confidence, respond with:
TITLE: unknown
YEAR: unknown
TYPE: unknown
CONFIDENCE: LOW
REASONING: [explain what you can tell about the content]"""
    })

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 500,
                    "messages": [
                        {
                            "role": "user",
                            "content": content,
                        }
                    ],
                },
            )

            if response.status_code != 200:
                logger.error(
                    f"AI identification API error: {response.status_code} - "
                    f"{response.text[:500]}"
                )
                return None

            data = response.json()
            response_text = data.get("content", [{}])[0].get("text", "")

            return _parse_ai_response(response_text)

    except Exception as e:
        logger.error(f"AI identification failed: {e}")
        return None


def _parse_ai_response(response_text: str) -> AIIdentificationResult | None:
    """Parse the AI response into a structured result.

    Args:
        response_text: Raw response text from Claude.

    Returns:
        AIIdentificationResult or None if parsing failed.
    """
    try:
        # Extract fields using regex
        title_match = re.search(r"TITLE:\s*(.+?)(?:\n|$)", response_text, re.IGNORECASE)
        year_match = re.search(r"YEAR:\s*(\d{4}|unknown)", response_text, re.IGNORECASE)
        type_match = re.search(r"TYPE:\s*(MOVIE|TV|unknown)", response_text, re.IGNORECASE)
        conf_match = re.search(r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", response_text, re.IGNORECASE)
        reason_match = re.search(r"REASONING:\s*(.+?)(?:\n\n|$)", response_text, re.IGNORECASE | re.DOTALL)

        title = title_match.group(1).strip() if title_match else None
        if title and title.lower() == "unknown":
            title = None

        year = None
        if year_match:
            year_str = year_match.group(1)
            if year_str.lower() != "unknown":
                year = int(year_str)

        is_movie = True
        if type_match:
            type_str = type_match.group(1).upper()
            is_movie = type_str != "TV"

        confidence = 0.5  # Default medium
        if conf_match:
            conf_str = conf_match.group(1).upper()
            confidence = {"HIGH": 0.85, "MEDIUM": 0.6, "LOW": 0.3}.get(conf_str, 0.5)

        reasoning = reason_match.group(1).strip() if reason_match else "No reasoning provided"

        logger.info(
            f"AI identified: {title} ({year}) - {confidence:.0%} confidence"
        )

        return AIIdentificationResult(
            title=title,
            year=year,
            confidence=confidence,
            reasoning=reasoning,
            is_movie=is_movie,
        )

    except Exception as e:
        logger.error(f"Failed to parse AI response: {e}")
        return None
