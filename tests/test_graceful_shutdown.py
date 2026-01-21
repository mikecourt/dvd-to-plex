"""Tests for graceful shutdown handling."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dvdtoplex.main import GracefulShutdown


class TestGracefulShutdown:
    """Tests for GracefulShutdown class."""

    def test_initial_state(self) -> None:
        """Shutdown should not be active initially."""
        shutdown = GracefulShutdown()
        assert shutdown.is_shutting_down is False

    def test_first_signal_initiates_shutdown(self) -> None:
        """First shutdown signal should initiate graceful shutdown."""
        shutdown = GracefulShutdown()
        shutdown.request_shutdown()
        assert shutdown.is_shutting_down is True

    def test_second_signal_forces_exit(self) -> None:
        """Second signal during shutdown should force exit."""
        shutdown = GracefulShutdown()
        shutdown.request_shutdown()

        with pytest.raises(SystemExit) as exc_info:
            shutdown.request_shutdown()

        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_wait_for_shutdown_blocks_until_signal(self) -> None:
        """wait_for_shutdown should block until shutdown is requested."""
        shutdown = GracefulShutdown()

        # Create a task that waits for shutdown
        wait_task = asyncio.create_task(shutdown.wait_for_shutdown())

        # Give it a moment to start waiting
        await asyncio.sleep(0.01)
        assert not wait_task.done()

        # Request shutdown
        shutdown.request_shutdown()

        # Wait should complete
        await asyncio.wait_for(wait_task, timeout=1.0)
        assert wait_task.done()

    @pytest.mark.asyncio
    async def test_wait_for_shutdown_returns_immediately_if_already_shutdown(
        self,
    ) -> None:
        """wait_for_shutdown should return immediately if shutdown already requested."""
        shutdown = GracefulShutdown()
        shutdown.request_shutdown()

        # Should complete immediately
        await asyncio.wait_for(shutdown.wait_for_shutdown(), timeout=0.1)


class TestApplicationShutdown:
    """Tests for Application shutdown behavior using direct service injection."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create a mock configuration."""
        config = MagicMock()
        config.workspace_dir = MagicMock()
        config.staging_dir = MagicMock()
        config.encoding_dir = MagicMock()
        config.database_path = MagicMock()
        config.web_host = "127.0.0.1"
        config.web_port = 8080
        return config

    @pytest.mark.asyncio
    async def test_stop_services_order(self, mock_config: MagicMock) -> None:
        """Services should be stopped in reverse order."""
        # Track stop order
        stop_order: list[str] = []

        mock_drive_watcher = AsyncMock()
        mock_rip_queue = AsyncMock()
        mock_encode_queue = AsyncMock()
        mock_identifier = AsyncMock()

        async def track_identifier() -> None:
            stop_order.append("identifier")

        async def track_encode_queue() -> None:
            stop_order.append("encode_queue")

        async def track_rip_queue() -> None:
            stop_order.append("rip_queue")

        async def track_drive_watcher() -> None:
            stop_order.append("drive_watcher")

        mock_identifier.stop = track_identifier
        mock_encode_queue.stop = track_encode_queue
        mock_rip_queue.stop = track_rip_queue
        mock_drive_watcher.stop = track_drive_watcher

        # Patch the classes directly where they're used
        with (
            patch("dvdtoplex.main.Database"),
            patch("dvdtoplex.main.DriveWatcher", return_value=mock_drive_watcher),
            patch("dvdtoplex.main.RipQueue", return_value=mock_rip_queue),
            patch("dvdtoplex.main.EncodeQueue", return_value=mock_encode_queue),
            patch("dvdtoplex.main.IdentifierService", return_value=mock_identifier),
        ):
            from dvdtoplex.main import Application

            app = Application(mock_config)
            await app.stop_services()

            # Verify order: identifier, encode_queue, rip_queue, drive_watcher
            assert stop_order == [
                "identifier",
                "encode_queue",
                "rip_queue",
                "drive_watcher",
            ]

    @pytest.mark.asyncio
    async def test_stop_services_handles_timeout(self, mock_config: MagicMock) -> None:
        """Stop should handle services that timeout."""
        mock_drive_watcher = AsyncMock()
        mock_rip_queue = AsyncMock()
        mock_encode_queue = AsyncMock()
        mock_identifier = AsyncMock()

        # Make identifier hang
        async def hang() -> None:
            await asyncio.sleep(100)

        mock_identifier.stop = hang

        # Patch the classes directly where they're used
        with (
            patch("dvdtoplex.main.Database"),
            patch("dvdtoplex.main.DriveWatcher", return_value=mock_drive_watcher),
            patch("dvdtoplex.main.RipQueue", return_value=mock_rip_queue),
            patch("dvdtoplex.main.EncodeQueue", return_value=mock_encode_queue),
            patch("dvdtoplex.main.IdentifierService", return_value=mock_identifier),
        ):
            from dvdtoplex.main import Application

            app = Application(mock_config)

            # Should complete without hanging (timeout should work)
            await asyncio.wait_for(app.stop_services(), timeout=10.0)

    @pytest.mark.asyncio
    async def test_cleanup_closes_database(self, mock_config: MagicMock) -> None:
        """Cleanup should close database connection."""
        mock_database = AsyncMock()

        # Patch the classes directly where they're used
        with (
            patch("dvdtoplex.main.Database", return_value=mock_database),
            patch("dvdtoplex.main.DriveWatcher"),
            patch("dvdtoplex.main.RipQueue"),
            patch("dvdtoplex.main.EncodeQueue"),
            patch("dvdtoplex.main.IdentifierService"),
        ):
            from dvdtoplex.main import Application

            app = Application(mock_config)
            await app.cleanup()

            mock_database.close.assert_called_once()
