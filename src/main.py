"""Main application entry point for Whoopster.

This module initializes the database, runs migrations, and starts
the scheduler for periodic data synchronization.
"""

import asyncio
import signal
import sys
from typing import Optional

from src.config import settings
from src.database.init_db import init_database
from src.scheduler.job_scheduler import initialize_scheduler, get_scheduler
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class Application:
    """
    Main application class for Whoopster.

    Manages application lifecycle including database initialization,
    scheduler startup, and graceful shutdown.
    """

    def __init__(self) -> None:
        """Initialize application."""
        self.scheduler = None
        self.shutdown_event = asyncio.Event()

        logger.info(
            "Application initialized",
            environment=settings.environment,
            log_level=settings.log_level,
        )

    async def startup(self) -> None:
        """
        Perform application startup tasks.

        - Initialize database connection
        - Run migrations
        - Start scheduler
        """
        logger.info("Starting application startup sequence")

        # Initialize database and run migrations
        logger.info("Initializing database")
        if not init_database():
            logger.error("Database initialization failed")
            sys.exit(1)

        logger.info("Database initialized successfully")

        # Initialize and start scheduler
        logger.info("Initializing scheduler")
        self.scheduler = await initialize_scheduler()

        logger.info(
            "Application startup complete",
            sync_interval_minutes=settings.sync_interval_minutes,
        )

    async def shutdown(self) -> None:
        """
        Perform graceful application shutdown.

        - Stop scheduler
        - Wait for running jobs to complete
        """
        logger.info("Starting application shutdown")

        if self.scheduler:
            logger.info("Shutting down scheduler")
            self.scheduler.shutdown(wait=True)

        logger.info("Application shutdown complete")

    def setup_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Setup signal handlers for graceful shutdown.

        Args:
            loop: Asyncio event loop
        """

        def signal_handler(sig_name: str) -> None:
            """Handle shutdown signals."""
            logger.info(
                "Received shutdown signal",
                signal=sig_name,
            )
            self.shutdown_event.set()

        # Register signal handlers using asyncio (works properly with async code)
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: signal_handler(signal.Signals(s).name),
            )

        logger.debug("Signal handlers registered for SIGTERM and SIGINT")

    async def run(self) -> None:
        """
        Run the application.

        Starts the scheduler and waits for shutdown signal.
        """
        try:
            # Setup signal handlers with current event loop
            loop = asyncio.get_running_loop()
            self.setup_signal_handlers(loop)

            # Perform startup tasks
            await self.startup()

            # Log running state
            logger.info(
                "Application running",
                message="Periodic data sync active. Press Ctrl+C to stop.",
            )

            # Wait for shutdown signal
            await self.shutdown_event.wait()

        except Exception as e:
            logger.error(
                "Application error",
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            # Perform shutdown tasks
            await self.shutdown()


async def main() -> None:
    """
    Main entry point.

    Creates and runs the application.
    """
    logger.info(
        "Whoopster starting",
        version="1.0.0",
        environment=settings.environment,
    )

    app = Application()

    try:
        await app.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(
            "Fatal error",
            error=str(e),
            exc_info=True,
        )
        sys.exit(1)

    logger.info("Whoopster stopped")


if __name__ == "__main__":
    """Run the application when executed directly."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handled in main()
        pass
