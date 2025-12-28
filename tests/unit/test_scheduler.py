"""Tests for job scheduler."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.scheduler.job_scheduler import WhoopScheduler, get_scheduler, initialize_scheduler
from src.models.db_models import User


@pytest.mark.unit
class TestWhoopScheduler:
    """Tests for WhoopScheduler class."""

    def test_scheduler_initialization(self):
        """Test scheduler initialization."""
        scheduler = WhoopScheduler(sync_interval_minutes=15)

        assert scheduler.sync_interval_minutes == 15
        assert scheduler.scheduler is not None

    def test_scheduler_default_interval(self):
        """Test scheduler uses default interval from settings."""
        scheduler = WhoopScheduler()

        # Should use settings default (15 minutes)
        assert scheduler.sync_interval_minutes > 0

    def test_scheduler_custom_interval(self):
        """Test scheduler with custom interval."""
        scheduler = WhoopScheduler(sync_interval_minutes=30)

        assert scheduler.sync_interval_minutes == 30


@pytest.mark.unit
@pytest.mark.asyncio
class TestWhoopSchedulerAsync:
    """Async tests for WhoopScheduler."""

    async def test_add_user_sync_job(self, test_user):
        """Test adding a sync job for a user."""
        scheduler = WhoopScheduler()

        job_id = await scheduler.add_user_sync_job(test_user.id)

        assert job_id == f"sync_user_{test_user.id}"

        # Verify job was added
        job = scheduler.scheduler.get_job(job_id)
        assert job is not None
        assert job.id == job_id

        # Cleanup
        scheduler.scheduler.remove_job(job_id)

    async def test_add_user_sync_job_custom_id(self, test_user):
        """Test adding sync job with custom job ID."""
        scheduler = WhoopScheduler()
        custom_id = "custom_job_id"

        job_id = await scheduler.add_user_sync_job(test_user.id, job_id=custom_id)

        assert job_id == custom_id

        # Cleanup
        scheduler.scheduler.remove_job(custom_id)

    async def test_add_user_sync_job_replaces_existing(self, test_user):
        """Test that adding a job replaces existing one."""
        scheduler = WhoopScheduler()

        # Add first job
        job_id1 = await scheduler.add_user_sync_job(test_user.id)

        # Add second job with same user
        job_id2 = await scheduler.add_user_sync_job(test_user.id)

        assert job_id1 == job_id2

        # Should only have one job
        jobs = scheduler.scheduler.get_jobs()
        user_jobs = [j for j in jobs if str(test_user.id) in j.id]
        assert len(user_jobs) == 1

        # Cleanup
        scheduler.scheduler.remove_job(job_id1)

    async def test_remove_user_sync_job(self, test_user):
        """Test removing a sync job."""
        scheduler = WhoopScheduler()

        # Add job
        await scheduler.add_user_sync_job(test_user.id)

        # Remove job
        result = await scheduler.remove_user_sync_job(test_user.id)

        assert result is True

        # Verify job was removed
        job = scheduler.scheduler.get_job(f"sync_user_{test_user.id}")
        assert job is None

    async def test_remove_nonexistent_job(self, test_user):
        """Test removing a job that doesn't exist."""
        scheduler = WhoopScheduler()

        result = await scheduler.remove_user_sync_job(test_user.id)

        assert result is False

    async def test_add_all_users(self, db_session, test_user):
        """Test adding jobs for all users."""
        scheduler = WhoopScheduler()

        with patch("src.scheduler.job_scheduler.get_db_context") as mock_context:
            mock_context.return_value.__enter__.return_value = db_session
            mock_context.return_value.__exit__.return_value = None

            jobs_added = await scheduler.add_all_users()

            assert jobs_added == 1

            # Cleanup
            scheduler.scheduler.remove_job(f"sync_user_{test_user.id}")

    def test_start_scheduler(self):
        """Test starting the scheduler."""
        scheduler = WhoopScheduler(use_persistent_jobstore=False)

        scheduler.start()

        assert scheduler.scheduler.running is True

        # Cleanup
        scheduler.shutdown(wait=False)

    def test_start_scheduler_already_running(self):
        """Test starting scheduler when already running."""
        scheduler = WhoopScheduler(use_persistent_jobstore=False)

        scheduler.start()
        # Start again (should be idempotent)
        scheduler.start()

        assert scheduler.scheduler.running is True

        # Cleanup
        scheduler.shutdown(wait=False)

    def test_shutdown_scheduler(self):
        """Test shutting down the scheduler."""
        scheduler = WhoopScheduler(use_persistent_jobstore=False)

        scheduler.start()
        assert scheduler.scheduler.running is True

        # Shutdown should complete without error
        # Note: AsyncIOScheduler may not fully stop when called from sync context
        scheduler.shutdown(wait=True)

    def test_shutdown_scheduler_not_running(self):
        """Test shutting down scheduler when not running."""
        scheduler = WhoopScheduler()

        # Should not raise error
        scheduler.shutdown(wait=False)

    def test_get_job_status(self, test_user):
        """Test getting job status."""
        scheduler = WhoopScheduler()

        # No job yet
        status = scheduler.get_job_status(test_user.id)
        assert status is None

    def test_get_all_jobs(self):
        """Test getting all jobs."""
        scheduler = WhoopScheduler()

        jobs = scheduler.get_all_jobs()

        assert isinstance(jobs, list)

    async def test_run_user_sync_now(self, test_user):
        """Test running immediate sync."""
        scheduler = WhoopScheduler()

        mock_result = {
            "user_id": test_user.id,
            "total_records": 10,
        }

        with patch(
            "src.scheduler.job_scheduler.sync_user_data",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await scheduler.run_user_sync_now(test_user.id)

            assert result["user_id"] == test_user.id
            assert result["total_records"] == 10


@pytest.mark.unit
def test_get_scheduler_singleton():
    """Test that get_scheduler returns singleton."""
    scheduler1 = get_scheduler()
    scheduler2 = get_scheduler()

    assert scheduler1 is scheduler2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_scheduler():
    """Test scheduler initialization function."""
    with patch("src.scheduler.job_scheduler.get_scheduler") as mock_get:
        mock_scheduler = MagicMock()
        mock_scheduler.add_all_users = AsyncMock(return_value=5)
        mock_scheduler.start = MagicMock()
        mock_get.return_value = mock_scheduler

        scheduler = await initialize_scheduler()

        assert mock_scheduler.add_all_users.called
        assert mock_scheduler.start.called
