"""Data collection orchestrator for Whoop data sync.

This module coordinates the synchronization of all Whoop data types
(sleep, recovery, workouts, cycles) using individual services.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from src.api.whoop_client import WhoopClient
from src.auth.token_manager import TokenManager
from src.api.rate_limiter import RateLimiter
from src.services.sleep_service import SleepService
from src.services.recovery_service import RecoveryService
from src.services.workout_service import WorkoutService
from src.services.cycle_service import CycleService
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DataCollector:
    """
    Orchestrates data synchronization for all Whoop data types.

    Coordinates sleep, recovery, workout, and cycle services to sync
    all user data from the Whoop API.

    Attributes:
        user_id: Database user ID
        whoop_client: Whoop API client instance
        sleep_service: Sleep data service
        recovery_service: Recovery data service
        workout_service: Workout data service
        cycle_service: Cycle data service
    """

    def __init__(
        self,
        user_id: int,
        token_manager: Optional[TokenManager] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        """
        Initialize data collector.

        Args:
            user_id: Database user ID
            token_manager: Token manager instance (creates new if None)
            rate_limiter: Rate limiter instance (creates new if None)
        """
        self.user_id = user_id

        # Initialize API client
        self.token_manager = token_manager or TokenManager()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.whoop_client = WhoopClient(
            user_id=user_id,
            token_manager=self.token_manager,
            rate_limiter=self.rate_limiter,
        )

        # Initialize services
        self.sleep_service = SleepService(user_id, self.whoop_client)
        self.recovery_service = RecoveryService(user_id, self.whoop_client)
        self.workout_service = WorkoutService(user_id, self.whoop_client)
        self.cycle_service = CycleService(user_id, self.whoop_client)

        logger.info("Data collector initialized", user_id=user_id)

    async def sync_all_data(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        data_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Sync all Whoop data types.

        Runs all service syncs concurrently for efficiency.

        Args:
            start: Start date for records (uses last sync if None)
            end: End date for records
            data_types: List of data types to sync (all if None)
                       Options: "sleep", "recovery", "workout", "cycle"

        Returns:
            Dictionary with sync results for each data type
        """
        logger.info(
            "Starting full data sync",
            user_id=self.user_id,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
            data_types=data_types,
        )

        # Determine which data types to sync
        all_data_types = ["sleep", "recovery", "workout", "cycle"]
        data_types = data_types or all_data_types

        # Validate data types
        invalid_types = set(data_types) - set(all_data_types)
        if invalid_types:
            raise ValueError(f"Invalid data types: {invalid_types}")

        # Create tasks for concurrent execution
        tasks = []
        sync_map = {}

        if "sleep" in data_types:
            task = asyncio.create_task(
                self.sleep_service.sync_sleep_records(start=start, end=end)
            )
            tasks.append(task)
            sync_map[task] = "sleep"

        if "recovery" in data_types:
            task = asyncio.create_task(
                self.recovery_service.sync_recovery_records(start=start, end=end)
            )
            tasks.append(task)
            sync_map[task] = "recovery"

        if "workout" in data_types:
            task = asyncio.create_task(
                self.workout_service.sync_workout_records(start=start, end=end)
            )
            tasks.append(task)
            sync_map[task] = "workout"

        if "cycle" in data_types:
            task = asyncio.create_task(
                self.cycle_service.sync_cycle_records(start=start, end=end)
            )
            tasks.append(task)
            sync_map[task] = "cycle"

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        sync_results = {}
        for task, result in zip(tasks, results):
            data_type = sync_map[task]

            if isinstance(result, Exception):
                logger.error(
                    "Sync failed for data type",
                    data_type=data_type,
                    error=str(result),
                    exc_info=result,
                )
                sync_results[data_type] = {
                    "status": "error",
                    "error": str(result),
                    "records_synced": 0,
                }
            else:
                logger.info(
                    "Sync completed for data type",
                    data_type=data_type,
                    records_synced=result,
                )
                sync_results[data_type] = {
                    "status": "success",
                    "records_synced": result,
                }

        # Calculate totals
        total_records = sum(
            r.get("records_synced", 0)
            for r in sync_results.values()
            if r["status"] == "success"
        )

        total_errors = sum(1 for r in sync_results.values() if r["status"] == "error")

        logger.info(
            "Full data sync completed",
            user_id=self.user_id,
            total_records=total_records,
            total_errors=total_errors,
            results=sync_results,
        )

        return {
            "user_id": self.user_id,
            "sync_time": datetime.now(timezone.utc).isoformat(),
            "total_records": total_records,
            "total_errors": total_errors,
            "results": sync_results,
        }

    async def sync_sleep(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """
        Sync only sleep data.

        Args:
            start: Start date for records
            end: End date for records

        Returns:
            Number of records synced
        """
        return await self.sleep_service.sync_sleep_records(start=start, end=end)

    async def sync_recovery(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """
        Sync only recovery data.

        Args:
            start: Start date for records
            end: End date for records

        Returns:
            Number of records synced
        """
        return await self.recovery_service.sync_recovery_records(start=start, end=end)

    async def sync_workouts(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """
        Sync only workout data.

        Args:
            start: Start date for records
            end: End date for records

        Returns:
            Number of records synced
        """
        return await self.workout_service.sync_workout_records(start=start, end=end)

    async def sync_cycles(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """
        Sync only cycle data.

        Args:
            start: Start date for records
            end: End date for records

        Returns:
            Number of records synced
        """
        return await self.cycle_service.sync_cycle_records(start=start, end=end)

    async def get_all_statistics(self) -> Dict[str, Any]:
        """
        Get statistics for all data types.

        Returns:
            Dictionary with stats for each data type
        """
        logger.info("Fetching statistics", user_id=self.user_id)

        # Fetch all statistics concurrently
        sleep_stats, recovery_stats, workout_stats, cycle_stats = await asyncio.gather(
            self.sleep_service.get_sleep_statistics(),
            self.recovery_service.get_recovery_statistics(),
            self.workout_service.get_workout_statistics(),
            self.cycle_service.get_cycle_statistics(),
        )

        return {
            "user_id": self.user_id,
            "sleep": sleep_stats,
            "recovery": recovery_stats,
            "workout": workout_stats,
            "cycle": cycle_stats,
        }

    async def verify_token(self) -> bool:
        """
        Verify user has valid OAuth token.

        Returns:
            True if valid token exists, False otherwise
        """
        return await self.token_manager.is_token_valid(self.user_id)


# Convenience function for scheduled sync jobs
async def sync_user_data(user_id: int) -> Dict[str, Any]:
    """
    Convenience function to sync all data for a user.

    This is the main entry point for scheduled sync jobs.

    Args:
        user_id: Database user ID

    Returns:
        Sync results dictionary
    """
    collector = DataCollector(user_id)
    return await collector.sync_all_data()
