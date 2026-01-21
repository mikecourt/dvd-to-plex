"""Tests for graceful shutdown functionality."""

import asyncio
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from dvdtoplex.config import Config
from dvdtoplex.database import Database
from dvdtoplex.services.base import BaseService
from dvdtoplex.services.drive_watcher import DriveWatcher
from dvdtoplex.services.rip_queue import RipQueue
from dvdtoplex.services.encode_queue import EncodeQueue
from dvdtoplex.services.identifier import IdentifierService
from dvdtoplex.main import Application


class TestBaseService:
    """Tests for BaseService stop functionality."""

    @pytest.mark.asyncio
    async def test_service_starts_and_stops(self) -> None:
        """Test that a service can be started and stopped."""

        class TestService(BaseService):
            def __init__(self) -> None:
                super().__init__("TestService")
                self.run_count = 0

            async def _run(self) -> None:
                while not self.should_stop():
                    self.run_count += 1
                    if await self.wait_for_stop(timeout=0.1):
                        break

        service = TestService()
        assert not service.is_running

        await service.start()
        assert service.is_running

        # Let it run briefly
        await asyncio.sleep(0.2)

        await service.stop()
        assert not service.is_running
        assert service.run_count > 0

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """Test that calling stop multiple times is safe."""

        class SimpleService(BaseService):
            async def _run(self) -> None:
                await self.wait_for_stop()

        service = SimpleService("Simple")
        await service.start()
        await service.stop()
        # Second stop should not raise
        await service.stop()
        assert not service.is_running

    @pytest.mark.asyncio
    async def test_stop_unstarted_service(self) -> None:
        """Test that stopping an unstarted service is safe."""

        class SimpleService(BaseService):
            async def _run(self) -> None:
                await self.wait_for_stop()

        service = SimpleService("Simple")
        # Should not raise
        await service.stop()
        assert not service.is_running


class TestDatabase:
    """Tests for Database close functionality."""

    @pytest.mark.asyncio
    async def test_database_close(self) -> None:
        """Test that database can be closed."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)

            await db.initialize()
            assert not db.is_closed

            await db.close()
            assert db.is_closed

    @pytest.mark.asyncio
    async def test_database_close_idempotent(self) -> None:
        """Test that closing database multiple times is safe."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)

            await db.initialize()
            await db.close()
            # Second close should not raise
            await db.close()
            assert db.is_closed

    @pytest.mark.asyncio
    async def test_database_operations_fail_after_close(self) -> None:
        """Test that database operations fail after close."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)

            await db.initialize()
            await db.close()

            with pytest.raises(RuntimeError, match="not connected"):
                _ = db.connection


class TestDriveWatcher:
    """Tests for DriveWatcher stop functionality."""

    @pytest.mark.asyncio
    async def test_drive_watcher_stop(self) -> None:
        """Test DriveWatcher stops gracefully."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            await db.initialize()

            config = Config(workspace_dir=Path(tmpdir), drive_poll_interval=0.1)
            watcher = DriveWatcher(config, db, drive_ids=["0"])
            await watcher.start()
            assert watcher.is_running

            await watcher.stop()
            assert not watcher.is_running

            await db.close()


class TestRipQueue:
    """Tests for RipQueue stop functionality."""

    @pytest.mark.asyncio
    async def test_rip_queue_stop(self) -> None:
        """Test RipQueue stops gracefully."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            await db.initialize()

            config = Config(workspace_dir=Path(tmpdir), drive_poll_interval=0.1)
            queue = RipQueue(config, db, drive_ids=["0"])
            await queue.start()
            assert queue.is_running

            await queue.stop()
            assert not queue.is_running

            await db.close()


class TestEncodeQueue:
    """Tests for EncodeQueue stop functionality."""

    @pytest.mark.asyncio
    async def test_encode_queue_stop(self) -> None:
        """Test EncodeQueue stops gracefully."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            await db.initialize()

            config = Config(workspace_dir=Path(tmpdir), drive_poll_interval=0.1)
            queue = EncodeQueue(config, db)
            await queue.start()
            assert queue.is_running

            await queue.stop()
            assert not queue.is_running

            await db.close()


class TestIdentifierService:
    """Tests for IdentifierService stop functionality."""

    @pytest.mark.asyncio
    async def test_identifier_service_stop(self) -> None:
        """Test IdentifierService stops gracefully."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            await db.initialize()

            config = Config(workspace_dir=Path(tmpdir), drive_poll_interval=0.1)
            service = IdentifierService(db, config)
            await service.start()
            assert service.is_running

            await service.stop()
            assert not service.is_running

            await db.close()


class TestApplication:
    """Tests for Application shutdown functionality."""

    @pytest.mark.asyncio
    async def test_application_shutdown(self) -> None:
        """Test full application shutdown."""
        with TemporaryDirectory() as tmpdir:
            config = Config(
                workspace_dir=Path(tmpdir),
                drive_poll_interval=0.1,
            )

            app = Application(config)
            await app.initialize()
            await app.start_services()

            # Verify services are running
            assert len(app.services) == 4
            for service in app.services:
                assert service.is_running

            # Shutdown
            await app.shutdown()

            # Verify everything is stopped
            assert len(app.services) == 0
            assert app.database.is_closed

    @pytest.mark.asyncio
    async def test_application_shutdown_stops_services_in_reverse_order(self) -> None:
        """Test that services are stopped in reverse start order."""
        stop_order: list[str] = []

        class TrackingService(BaseService):
            def __init__(self, name: str) -> None:
                super().__init__(name)
                self.stop_order = stop_order

            async def _run(self) -> None:
                await self.wait_for_stop()

            async def stop(self) -> None:
                self.stop_order.append(self.name)
                await super().stop()

        with TemporaryDirectory() as tmpdir:
            config = Config(workspace_dir=Path(tmpdir))
            app = Application(config)

            await app.initialize()

            # Replace services with tracking services
            app.services = [
                TrackingService("Service1"),
                TrackingService("Service2"),
                TrackingService("Service3"),
            ]

            for service in app.services:
                await service.start()

            await app.stop_services()

            # Verify reverse order (last started, first stopped)
            assert stop_order == ["Service3", "Service2", "Service1"]

            await app.close_database()

    @pytest.mark.asyncio
    async def test_application_shutdown_idempotent(self) -> None:
        """Test that shutdown can be called multiple times safely."""
        with TemporaryDirectory() as tmpdir:
            config = Config(
                workspace_dir=Path(tmpdir),
                drive_poll_interval=0.1,
            )

            app = Application(config)
            await app.initialize()
            await app.start_services()

            await app.shutdown()
            # Second shutdown should not raise
            await app.shutdown()

    @pytest.mark.asyncio
    async def test_application_initializes_directories(self) -> None:
        """Test that workspace directories are created on initialize."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            config = Config(workspace_dir=workspace)

            app = Application(config)
            await app.initialize()

            assert workspace.exists()
            assert (workspace / "staging").exists()
            assert (workspace / "encoding").exists()

            await app.shutdown()
