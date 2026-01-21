"""Main entry point for dvdtoplex."""

import asyncio
import logging
import signal
import sys
from typing import Protocol

import uvicorn

from dvdtoplex.config import Config, load_config
from dvdtoplex.database import Database
from dvdtoplex.services.drive_watcher import DriveWatcher
from dvdtoplex.services.rip_queue import RipQueue
from dvdtoplex.services.encode_queue import EncodeQueue
from dvdtoplex.services.identifier import IdentifierService
from dvdtoplex.services.file_mover import FileMover
from dvdtoplex.web.app import create_app


class Service(Protocol):
    """Protocol for services that can be started and stopped."""

    @property
    def is_running(self) -> bool:
        """Return True if the service is running."""
        ...

    @property
    def name(self) -> str:
        """Return the service name."""
        ...

    async def start(self) -> None:
        """Start the service."""
        ...

    async def stop(self) -> None:
        """Stop the service."""
        ...

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Manages graceful shutdown with support for forced exit on second signal."""

    def __init__(self) -> None:
        """Initialize shutdown handler."""
        self._shutdown_event = asyncio.Event()
        self._is_shutting_down = False

    @property
    def is_shutting_down(self) -> bool:
        """Return True if shutdown has been requested."""
        return self._is_shutting_down

    def request_shutdown(self) -> None:
        """Request graceful shutdown, or force exit if already shutting down."""
        if self._is_shutting_down:
            logger.warning("Forced shutdown requested")
            sys.exit(1)
        self._is_shutting_down = True
        self._shutdown_event.set()
        logger.info("Graceful shutdown requested")

    async def wait_for_shutdown(self) -> None:
        """Wait until shutdown is requested."""
        await self._shutdown_event.wait()


class Application:
    """Main application orchestrating all services."""

    def __init__(self, config: Config) -> None:
        """Initialize the application.

        Args:
            config: Application configuration.
        """
        self.config = config
        self._shutdown_event = asyncio.Event()
        self._web_server: uvicorn.Server | None = None

        # Create database instance (but don't connect yet)
        db_path = self.config.workspace_dir / "dvdtoplex.db"
        self.database: Database = Database(db_path)

        # Create services (but don't start yet)
        self.drive_watcher = DriveWatcher(self.config, self.database, self.config.drive_ids)
        rip_queue = RipQueue(self.config, self.database, self.config.drive_ids)
        encode_queue = EncodeQueue(self.config, self.database)
        identifier = IdentifierService(self.database, self.config)
        file_mover = FileMover(self.config, self.database)
        self.services: list[Service] = [self.drive_watcher, rip_queue, encode_queue, identifier, file_mover]

    async def _ensure_directories(self) -> None:
        """Create workspace directories if they don't exist."""
        self.config.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.config.staging_dir.mkdir(parents=True, exist_ok=True)
        self.config.encoding_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Initialize the application (directories, database)."""
        await self._ensure_directories()
        await self.database.initialize()

    async def start_services(self) -> None:
        """Start all services."""
        # Start all services (they were created in __init__)
        for service in self.services:
            await service.start()

    async def start_web_server(self) -> None:
        """Start the web server."""
        # Create FastAPI app with dependencies
        app = create_app(
            database=self.database,
            drive_watcher=self.drive_watcher,
            config=self.config,
        )

        # Configure uvicorn
        config = uvicorn.Config(
            app,
            host=self.config.web_host,
            port=self.config.web_port,
            log_level="info",
        )
        self._web_server = uvicorn.Server(config)

        # Run the server (this will block until shutdown)
        await self._web_server.serve()

    async def stop_web_server(self) -> None:
        """Stop the web server."""
        if self._web_server is not None:
            self._web_server.should_exit = True

    async def stop_services(self) -> None:
        """Stop all services in reverse order."""
        # Stop in reverse order (last started, first stopped)
        for service in reversed(self.services):
            try:
                await asyncio.wait_for(service.stop(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout stopping {service.name}")
            except Exception as e:
                logger.error(f"Error stopping {service.name}: {e}")

        self.services = []

    async def close_database(self) -> None:
        """Close the database connection."""
        await self.database.close()

    async def cleanup(self) -> None:
        """Clean up resources (alias for close_database)."""
        await self.close_database()

    async def shutdown(self) -> None:
        """Perform full application shutdown."""
        await self.stop_services()
        await self.close_database()

    async def stop(self) -> None:
        """Stop the application with logging."""
        logger.info("Stopping DVD to Plex application")
        await self.shutdown()
        logger.info("Application stopped")

    def _handle_shutdown_signal(self) -> None:
        """Handle shutdown signal (SIGTERM/SIGINT)."""
        self._shutdown_event.set()


async def main() -> None:
    """Main async entry point that orchestrates all services."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    config = load_config()
    shutdown = GracefulShutdown()
    app = Application(config)

    # Set up signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.request_shutdown)

    try:
        await app.initialize()
        await app.start_services()
        logger.info(f"DVD to Plex started. Web UI at http://{config.web_host}:{config.web_port}")

        # Run web server and wait for shutdown concurrently
        web_task = asyncio.create_task(app.start_web_server())
        shutdown_task = asyncio.create_task(shutdown.wait_for_shutdown())

        # Wait for either shutdown signal or web server to stop
        done, pending = await asyncio.wait(
            [web_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Stop web server if shutdown was requested
        await app.stop_web_server()
    finally:
        await app.stop()


def run() -> None:
    """Synchronous entry point for the CLI command."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
