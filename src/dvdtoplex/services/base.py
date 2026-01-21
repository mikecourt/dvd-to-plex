"""Base service class for DVD-to-Plex services."""

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseService(ABC):
    """Abstract base class for background services.

    All services should inherit from this class and implement:
    - _run(): The main service loop
    - stop(): Graceful shutdown (calls _stop_running() by default)

    Services run in a background task and can be stopped gracefully.
    """

    def __init__(self, name: str) -> None:
        """Initialize service with a name for logging."""
        self.name = name
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._logger = logging.getLogger(f"{__name__}.{name}")

    @property
    def is_running(self) -> bool:
        """Check if service is running."""
        return self._running

    async def start(self) -> None:
        """Start the service in a background task."""
        if self._running:
            self._logger.warning("Service %s is already running", self.name)
            return

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_wrapper())
        self._logger.info("Service %s started", self.name)

    async def _run_wrapper(self) -> None:
        """Wrapper around _run to handle exceptions and cleanup."""
        try:
            await self._run()
        except asyncio.CancelledError:
            self._logger.debug("Service %s was cancelled", self.name)
        except Exception:
            self._logger.exception("Service %s encountered an error", self.name)
        finally:
            self._running = False

    @abstractmethod
    async def _run(self) -> None:
        """Main service loop. Override in subclasses."""
        pass

    async def stop(self) -> None:
        """Stop the service gracefully.

        Sets the stop event and waits for the service task to complete.
        Subclasses can override this to add custom cleanup logic.
        """
        if not self._running:
            self._logger.debug("Service %s is not running", self.name)
            return

        self._logger.info("Stopping service %s...", self.name)
        self._stop_event.set()

        if self._task is not None:
            # Give the task a chance to finish gracefully
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._logger.warning(
                    "Service %s did not stop within timeout, cancelling", self.name
                )
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

        self._running = False
        self._logger.info("Service %s stopped", self.name)

    async def wait_for_stop(self, timeout: float | None = None) -> bool:
        """Wait for stop signal.

        Useful in service loops to check if shutdown was requested.
        Returns True if stop was requested, False if timeout occurred.
        """
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def should_stop(self) -> bool:
        """Check if stop has been requested."""
        return self._stop_event.is_set()
