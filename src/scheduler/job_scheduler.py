"""Job scheduler for periodic Whoop data synchronization.

This module configures APScheduler to run periodic data sync jobs
at configured intervals (default: 15 minutes).
"""

import asyncio
from typing import Optional, List
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from sqlalchemy import select

from src.config import settings
from src.services.data_collector import sync_user_data
from src.models.db_models import User
from src.database.session import get_db_context
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class WhoopScheduler:
    """
    Scheduler for periodic Whoop data synchronization.

    Uses APScheduler to run sync jobs at configured intervals.
    Jobs persist across restarts using PostgreSQL job store.

    Attributes:
        scheduler: APScheduler instance
        sync_interval_minutes: Minutes between sync runs
    """

    def __init__(
        self,
        sync_interval_minutes: Optional[int] = None,
        use_persistent_jobstore: bool = True,
    ) -> None:
        """
        Initialize scheduler.

        Args:
            sync_interval_minutes: Minutes between syncs (from settings if None)
            use_persistent_jobstore: Use PostgreSQL job store (False for in-memory testing)
        """
        self.sync_interval_minutes = (
            sync_interval_minutes or settings.sync_interval_minutes
        )

        # Configure job stores
        if use_persistent_jobstore:
            jobstores = {
                "default": SQLAlchemyJobStore(url=settings.database_url),
            }
        else:
            # Use in-memory job store for testing (empty dict = MemoryJobStore)
            jobstores = {}

        # Configure executors
        executors = {
            "default": AsyncIOExecutor(),
        }

        # Job defaults
        job_defaults = {
            "coalesce": True,  # Skip missed runs if service was down
            "max_instances": 1,  # Prevent concurrent runs
            "misfire_grace_time": 300,  # 5-minute tolerance for late starts
        }

        # Create scheduler
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="UTC",
        )

        logger.info(
            "Scheduler initialized",
            sync_interval_minutes=self.sync_interval_minutes,
        )

    async def add_user_sync_job(
        self,
        user_id: int,
        job_id: Optional[str] = None,
    ) -> str:
        """
        Add periodic sync job for a user.

        Args:
            user_id: Database user ID
            job_id: Optional job ID (auto-generated if None)

        Returns:
            Job ID
        """
        if job_id is None:
            job_id = f"sync_user_{user_id}"

        # Check if job already exists
        existing_job = self.scheduler.get_job(job_id)
        if existing_job:
            logger.warning(
                "Sync job already exists, removing old one",
                job_id=job_id,
                user_id=user_id,
            )
            self.scheduler.remove_job(job_id)

        # Add new job
        self.scheduler.add_job(
            func=sync_user_data,
            trigger=IntervalTrigger(minutes=self.sync_interval_minutes),
            args=[user_id],
            id=job_id,
            name=f"Sync Whoop data for user {user_id}",
            replace_existing=True,
        )

        logger.info(
            "Added user sync job",
            job_id=job_id,
            user_id=user_id,
            interval_minutes=self.sync_interval_minutes,
        )

        return job_id

    async def remove_user_sync_job(self, user_id: int) -> bool:
        """
        Remove sync job for a user.

        Args:
            user_id: Database user ID

        Returns:
            True if job removed, False if not found
        """
        job_id = f"sync_user_{user_id}"

        try:
            self.scheduler.remove_job(job_id)
            logger.info("Removed user sync job", job_id=job_id, user_id=user_id)
            return True
        except Exception as e:
            logger.warning(
                "Failed to remove sync job",
                job_id=job_id,
                user_id=user_id,
                error=str(e),
            )
            return False

    async def add_all_users(self) -> int:
        """
        Add sync jobs for all users in database.

        Returns:
            Number of jobs added
        """
        logger.info("Adding sync jobs for all users")

        with get_db_context() as db:
            stmt = select(User)
            users = db.execute(stmt).scalars().all()

            jobs_added = 0
            for user in users:
                try:
                    await self.add_user_sync_job(user.id)
                    jobs_added += 1
                except Exception as e:
                    logger.error(
                        "Failed to add sync job for user",
                        user_id=user.id,
                        error=str(e),
                        exc_info=True,
                    )

        logger.info("Added sync jobs", count=jobs_added, total_users=len(users))
        return jobs_added

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")
        else:
            logger.warning("Scheduler already running")

    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the scheduler.

        Args:
            wait: Wait for running jobs to complete
        """
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler shutdown", wait=wait)
        else:
            logger.warning("Scheduler not running")

    def get_job_status(self, user_id: int) -> Optional[dict]:
        """
        Get status of user's sync job.

        Args:
            user_id: Database user ID

        Returns:
            Job status dictionary or None if not found
        """
        job_id = f"sync_user_{user_id}"
        job = self.scheduler.get_job(job_id)

        if not job:
            return None

        return {
            "job_id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }

    def get_all_jobs(self) -> List[dict]:
        """
        Get status of all scheduled jobs.

        Returns:
            List of job status dictionaries
        """
        jobs = self.scheduler.get_jobs()

        return [
            {
                "job_id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in jobs
        ]

    async def run_user_sync_now(self, user_id: int) -> dict:
        """
        Trigger immediate sync for a user (outside schedule).

        Args:
            user_id: Database user ID

        Returns:
            Sync results
        """
        logger.info("Running immediate sync for user", user_id=user_id)

        try:
            result = await sync_user_data(user_id)
            logger.info(
                "Immediate sync completed",
                user_id=user_id,
                total_records=result.get("total_records"),
            )
            return result
        except Exception as e:
            logger.error(
                "Immediate sync failed",
                user_id=user_id,
                error=str(e),
                exc_info=True,
            )
            raise


# Global scheduler instance
_scheduler: Optional[WhoopScheduler] = None


def get_scheduler() -> WhoopScheduler:
    """
    Get or create global scheduler instance.

    Returns:
        WhoopScheduler instance
    """
    global _scheduler

    if _scheduler is None:
        _scheduler = WhoopScheduler()

    return _scheduler


async def initialize_scheduler() -> WhoopScheduler:
    """
    Initialize and start the scheduler with all users.

    This is the main entry point for scheduler setup.

    Returns:
        Started scheduler instance
    """
    logger.info("Initializing scheduler")

    scheduler = get_scheduler()

    # Add jobs for all existing users
    await scheduler.add_all_users()

    # Start scheduler
    scheduler.start()

    logger.info("Scheduler initialization complete")

    return scheduler
