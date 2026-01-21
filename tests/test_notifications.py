"""Tests for the notifications module."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from dvdtoplex.notifications import Notifier, NotificationResult, PUSHOVER_API_URL


class TestNotifier:
    """Tests for the Notifier class."""

    def test_init_with_credentials(self) -> None:
        """Test notifier initialization with credentials."""
        notifier = Notifier(user_key="test_user", api_token="test_token")
        assert notifier.user_key == "test_user"
        assert notifier.api_token == "test_token"

    def test_init_without_credentials(self) -> None:
        """Test notifier initialization without credentials."""
        notifier = Notifier()
        assert notifier.user_key is None
        assert notifier.api_token is None

    def test_has_credentials_true(self) -> None:
        """Test _has_credentials returns True when both are set."""
        notifier = Notifier(user_key="user", api_token="token")
        assert notifier._has_credentials() is True

    def test_has_credentials_false_no_user(self) -> None:
        """Test _has_credentials returns False when user_key is missing."""
        notifier = Notifier(user_key=None, api_token="token")
        assert notifier._has_credentials() is False

    def test_has_credentials_false_no_token(self) -> None:
        """Test _has_credentials returns False when api_token is missing."""
        notifier = Notifier(user_key="user", api_token=None)
        assert notifier._has_credentials() is False

    def test_has_credentials_false_empty_strings(self) -> None:
        """Test _has_credentials returns False for empty strings."""
        notifier = Notifier(user_key="", api_token="")
        assert notifier._has_credentials() is False


class TestNotifierSend:
    """Tests for the send method."""

    @pytest.mark.asyncio
    async def test_send_without_credentials(self) -> None:
        """Test send returns failure when credentials are missing."""
        notifier = Notifier()
        result = await notifier.send("Test Title", "Test message")

        assert result.success is False
        assert "not configured" in result.message

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        """Test successful notification send."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await notifier.send("Test Title", "Test message")

            assert result.success is True
            assert "successfully" in result.message

            mock_instance.post.assert_called_once()
            call_args = mock_instance.post.call_args
            assert call_args[0][0] == PUSHOVER_API_URL
            assert call_args[1]["data"]["token"] == "test_token"
            assert call_args[1]["data"]["user"] == "test_user"
            assert call_args[1]["data"]["title"] == "Test Title"
            assert call_args[1]["data"]["message"] == "Test message"
            assert call_args[1]["data"]["priority"] == 0

    @pytest.mark.asyncio
    async def test_send_with_priority(self) -> None:
        """Test send with custom priority."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await notifier.send("Test", "Message", priority=1)

            assert result.success is True
            call_args = mock_instance.post.call_args
            assert call_args[1]["data"]["priority"] == 1

    @pytest.mark.asyncio
    async def test_send_with_url(self) -> None:
        """Test send with optional URL."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await notifier.send(
                "Test", "Message", url="http://example.com/review"
            )

            assert result.success is True
            call_args = mock_instance.post.call_args
            assert call_args[1]["data"]["url"] == "http://example.com/review"

    @pytest.mark.asyncio
    async def test_send_http_error(self) -> None:
        """Test send handles HTTP errors gracefully."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=Mock(),
            response=mock_response,
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await notifier.send("Test", "Message")

            assert result.success is False
            assert "HTTP error" in result.message

    @pytest.mark.asyncio
    async def test_send_request_error(self) -> None:
        """Test send handles request errors gracefully."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = httpx.RequestError(
                "Connection failed", request=AsyncMock()
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await notifier.send("Test", "Message")

            assert result.success is False
            assert "Request error" in result.message


class TestNotifyDiscComplete:
    """Tests for the notify_disc_complete helper."""

    @pytest.mark.asyncio
    async def test_disc_complete_with_title_and_year(self) -> None:
        """Test notification with identified title and year."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        with patch.object(notifier, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = NotificationResult(True, "OK")

            result = await notifier.notify_disc_complete(
                disc_label="MY_MOVIE_DISC",
                title="The Matrix",
                year=1999,
            )

            assert result.success is True
            mock_send.assert_called_once_with(
                "Disc Complete",
                "MY_MOVIE_DISC identified as The Matrix (1999)",
                priority=0,
            )

    @pytest.mark.asyncio
    async def test_disc_complete_with_title_only(self) -> None:
        """Test notification with title but no year."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        with patch.object(notifier, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = NotificationResult(True, "OK")

            result = await notifier.notify_disc_complete(
                disc_label="MY_MOVIE_DISC",
                title="Unknown Movie",
            )

            assert result.success is True
            mock_send.assert_called_once_with(
                "Disc Complete",
                "MY_MOVIE_DISC identified as Unknown Movie",
                priority=0,
            )

    @pytest.mark.asyncio
    async def test_disc_complete_without_identification(self) -> None:
        """Test notification without identification."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        with patch.object(notifier, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = NotificationResult(True, "OK")

            result = await notifier.notify_disc_complete(disc_label="UNKNOWN_DISC")

            assert result.success is True
            mock_send.assert_called_once_with(
                "Disc Complete",
                "UNKNOWN_DISC has been processed",
                priority=0,
            )


class TestNotifyError:
    """Tests for the notify_error helper."""

    @pytest.mark.asyncio
    async def test_notify_error(self) -> None:
        """Test error notification."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        with patch.object(notifier, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = NotificationResult(True, "OK")

            result = await notifier.notify_error(
                disc_label="BAD_DISC",
                error_message="Failed to read disc",
            )

            assert result.success is True
            mock_send.assert_called_once_with(
                title="Ripping Error",
                message="BAD_DISC: Failed to read disc",
                priority=1,
            )


class TestNotifyReviewNeeded:
    """Tests for the notify_review_needed helper."""

    @pytest.mark.asyncio
    async def test_notify_review_needed(self) -> None:
        """Test review needed notification."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        with patch.object(notifier, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = NotificationResult(True, "OK")

            result = await notifier.notify_review_needed(
                disc_label="AMBIGUOUS_DISC",
                confidence=0.65,
                web_ui_url="http://localhost:8080/review",
            )

            assert result.success is True
            mock_send.assert_called_once_with(
                title="Review Needed",
                message="AMBIGUOUS_DISC needs review (65% confidence)",
                priority=0,
                url="http://localhost:8080/review",
            )

    @pytest.mark.asyncio
    async def test_notify_review_needed_low_confidence(self) -> None:
        """Test review notification with low confidence."""
        notifier = Notifier(user_key="test_user", api_token="test_token")

        with patch.object(notifier, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = NotificationResult(True, "OK")

            result = await notifier.notify_review_needed(
                disc_label="MYSTERY_DISC",
                confidence=0.23,
                web_ui_url="http://192.168.1.100:8080/review",
            )

            assert result.success is True
            mock_send.assert_called_once_with(
                title="Review Needed",
                message="MYSTERY_DISC needs review (23% confidence)",
                priority=0,
                url="http://192.168.1.100:8080/review",
            )


class TestNotificationResult:
    """Tests for the NotificationResult dataclass."""

    def test_notification_result_success(self) -> None:
        """Test successful notification result."""
        result = NotificationResult(success=True, message="OK")
        assert result.success is True
        assert result.message == "OK"

    def test_notification_result_failure(self) -> None:
        """Test failed notification result."""
        result = NotificationResult(success=False, message="Error occurred")
        assert result.success is False
        assert result.message == "Error occurred"


class TestMissingCredentialsLogging:
    """Tests for logging behavior with missing credentials."""

    @pytest.mark.asyncio
    async def test_missing_credentials_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that missing credentials logs a warning."""
        import logging

        notifier = Notifier()

        with caplog.at_level(logging.WARNING):
            await notifier.send("Test", "Message")

        assert "not configured" in caplog.text
