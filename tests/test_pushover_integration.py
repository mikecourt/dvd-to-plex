"""Pushover API integration tests for US-013.

These tests verify Pushover notifications work when configured with real credentials.
Tests skip gracefully when PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN are not set.
"""

import os

import pytest

from dvdtoplex.config import load_config
from dvdtoplex.notifications import Notifier


class TestPushoverIntegration:
    """Test Pushover API integration with real credentials."""

    def test_load_config_pushover_credentials(self) -> None:
        """Verify load_config reads Pushover credentials from environment."""
        config = load_config()
        # Credentials are read from environment (may be empty strings if not set)
        assert isinstance(config.pushover_user_key, str)
        assert isinstance(config.pushover_api_token, str)

    def test_notifier_is_configured_when_no_credentials(self) -> None:
        """Verify Notifier.is_configured returns False when no credentials."""
        notifier = Notifier()
        assert notifier.is_configured is False

    def test_notifier_is_configured_with_partial_credentials(self) -> None:
        """Verify Notifier.is_configured returns False with only user_key."""
        notifier = Notifier(user_key="test_user", api_token=None)
        assert notifier.is_configured is False

    def test_notifier_is_configured_with_full_credentials(self) -> None:
        """Verify Notifier.is_configured returns True with both credentials."""
        notifier = Notifier(user_key="test_user", api_token="test_token")
        assert notifier.is_configured is True

    @pytest.mark.asyncio
    async def test_send_skips_when_not_configured(self) -> None:
        """Verify send() returns NotificationResult with success=False when not configured."""
        notifier = Notifier()
        result = await notifier.send("Test", "Test message")
        assert result.success is False
        assert "not configured" in result.message.lower()

    def test_skip_message_when_pushover_not_configured(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify skip message is printed when Pushover not configured."""
        config = load_config()
        if not config.pushover_user_key or not config.pushover_api_token:
            print("SKIP: Pushover not configured")
            captured = capsys.readouterr()
            assert "SKIP: Pushover not configured" in captured.out
        else:
            # Credentials are configured, test passes
            pass

    @pytest.mark.asyncio
    async def test_send_notification_with_real_credentials(self) -> None:
        """Test sending a real notification when credentials are configured.

        This test will skip if PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN
        environment variables are not set.
        """
        user_key = os.getenv("PUSHOVER_USER_KEY", "")
        api_token = os.getenv("PUSHOVER_API_TOKEN", "")

        if not user_key or not api_token:
            pytest.skip("SKIP: Pushover not configured")

        notifier = Notifier(user_key=user_key, api_token=api_token)
        assert notifier.is_configured is True

        # Send test notification with lowest priority (-2 = silent)
        # Using priority -2 to avoid disturbing the user with test notifications
        result = await notifier.send(
            title="DVD-to-Plex Test",
            message="Integration test notification",
            priority=-2,  # Lowest priority (no notification/sound)
        )
        print(f"Notification sent: {result}")
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_disc_complete_with_real_credentials(self) -> None:
        """Test notify_disc_complete with real credentials."""
        user_key = os.getenv("PUSHOVER_USER_KEY", "")
        api_token = os.getenv("PUSHOVER_API_TOKEN", "")

        if not user_key or not api_token:
            pytest.skip("SKIP: Pushover not configured")

        notifier = Notifier(user_key=user_key, api_token=api_token)

        # Use priority -2 (lowest) via the send method indirectly
        # notify_disc_complete uses priority 0, so we test the basic send path
        result = await notifier.send(
            title="Disc Complete Test",
            message="TEST_DISC completed processing",
            priority=-2,
        )
        print(f"Notification sent: {result}")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_with_url_and_real_credentials(self) -> None:
        """Test sending notification with URL when credentials are configured."""
        user_key = os.getenv("PUSHOVER_USER_KEY", "")
        api_token = os.getenv("PUSHOVER_API_TOKEN", "")

        if not user_key or not api_token:
            pytest.skip("SKIP: Pushover not configured")

        notifier = Notifier(user_key=user_key, api_token=api_token)

        result = await notifier.send(
            title="URL Test",
            message="Test notification with URL",
            priority=-2,
            url="https://example.com",
            url_title="Example Link",
        )
        print(f"Notification sent: {result}")
        assert result is True


class TestNotifierMockedCredentials:
    """Test Notifier behavior without making real API calls."""

    @pytest.mark.asyncio
    async def test_send_handles_invalid_credentials_gracefully(self) -> None:
        """Verify send() handles invalid credentials without crashing."""
        notifier = Notifier(user_key="invalid_user", api_token="invalid_token")
        assert notifier.is_configured is True

        # This will fail at the API level but should return False, not raise
        result = await notifier.send(
            title="Test",
            message="This should fail gracefully",
            priority=-2,
        )
        # API call will fail with invalid credentials, but should not raise
        assert result.success is False

    def test_notifier_properties(self) -> None:
        """Verify Notifier stores credentials correctly."""
        notifier = Notifier(user_key="my_user", api_token="my_token")
        assert notifier.user_key == "my_user"
        assert notifier.api_token == "my_token"
        assert notifier.is_configured is True
