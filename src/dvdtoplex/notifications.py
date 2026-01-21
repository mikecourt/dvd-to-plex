"""Pushover notification integration."""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"


@dataclass
class NotificationResult:
    """Result of a notification attempt."""

    success: bool
    message: str | None = None
    error: str | None = None


class Notifier:
    """Pushover notification sender."""

    def __init__(
        self,
        user_key: str | None = None,
        api_token: str | None = None,
    ) -> None:
        """Initialize notifier.

        Args:
            user_key: Pushover user key (optional).
            api_token: Pushover API token (optional).
        """
        self.user_key = user_key
        self.api_token = api_token

    def _has_credentials(self) -> bool:
        """Check if credentials are configured."""
        return bool(self.user_key and self.api_token)

    @property
    def is_configured(self) -> bool:
        """Check if credentials are configured."""
        return self._has_credentials()

    async def send(
        self,
        title: str,
        message: str,
        priority: int = 0,
        url: str | None = None,
        url_title: str | None = None,
    ) -> NotificationResult:
        """Send a notification via Pushover.

        Args:
            title: Notification title.
            message: Notification message.
            priority: Priority level (-2 to 2).
            url: Optional URL to include.
            url_title: Optional title for the URL.

        Returns:
            NotificationResult with success status and message.
        """
        if not self.is_configured:
            logger.warning("Pushover credentials not configured, skipping notification")
            return NotificationResult(
                success=False, message="Credentials not configured"
            )

        try:
            # At this point we know credentials are set (checked by is_configured)
            assert self.api_token is not None
            assert self.user_key is not None
            data: dict[str, str | int] = {
                "token": self.api_token,
                "user": self.user_key,
                "title": title,
                "message": message,
                "priority": priority,
            }

            if url:
                data["url"] = url
            if url_title:
                data["url_title"] = url_title

            async with httpx.AsyncClient() as client:
                response = await client.post(PUSHOVER_API_URL, data=data)
                response.raise_for_status()
                return NotificationResult(
                    success=True, message="Notification sent successfully"
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending Pushover notification: {e}")
            return NotificationResult(success=False, message=f"HTTP error: {e}")

        except httpx.RequestError as e:
            logger.error(f"Request error sending Pushover notification: {e}")
            return NotificationResult(success=False, message=f"Request error: {e}")

        except Exception as e:
            logger.error(f"Error sending Pushover notification: {e}")
            return NotificationResult(success=False, message=str(e))

    async def notify_disc_complete(
        self,
        disc_label: str,
        title: str | None = None,
        year: int | None = None,
    ) -> NotificationResult:
        """Notify that a disc has completed processing.

        Args:
            disc_label: Label of the completed disc.
            title: Identified title, if known.
            year: Year of the title, if known.

        Returns:
            NotificationResult with success status.
        """
        msg_title = "Disc Complete"
        if title and year:
            message = f"{disc_label} identified as {title} ({year})"
        elif title:
            message = f"{disc_label} identified as {title}"
        else:
            message = f"{disc_label} has been processed"

        return await self.send(msg_title, message, priority=0)

    async def notify_error(
        self,
        disc_label: str,
        error_message: str,
    ) -> NotificationResult:
        """Notify of a processing error.

        Args:
            disc_label: Label of the disc that errored.
            error_message: Error message.

        Returns:
            NotificationResult with success status.
        """
        return await self.send(
            title="Ripping Error",
            message=f"{disc_label}: {error_message}",
            priority=1,
        )

    async def notify_review_needed(
        self,
        disc_label: str,
        confidence: float,
        web_ui_url: str,
    ) -> NotificationResult:
        """Notify that manual review is needed.

        Args:
            disc_label: Label of the disc needing review.
            confidence: Confidence score.
            web_ui_url: URL to the review page.

        Returns:
            NotificationResult with success status.
        """
        message = f"{disc_label} needs review ({confidence:.0%} confidence)"

        return await self.send(
            title="Review Needed",
            message=message,
            priority=0,
            url=web_ui_url,
        )
