"""Service for managing sleep data from Whoop API.

This module handles fetching sleep records from the Whoop API,
transforming them to database models, and performing upsert operations.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.api.whoop_client import WhoopClient
from src.models.db_models import SleepRecord, SyncStatus
from src.database.session import get_db_context
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class SleepService:
    """
    Service for managing sleep data.

    Handles fetching sleep records from Whoop API and storing/updating
    them in the database with upsert logic.

    Attributes:
        whoop_client: Whoop API client instance
        user_id: Database user ID
    """

    def __init__(self, user_id: int, whoop_client: WhoopClient) -> None:
        """
        Initialize sleep service.

        Args:
            user_id: Database user ID
            whoop_client: Whoop API client instance
        """
        self.user_id = user_id
        self.whoop_client = whoop_client

        logger.info("Sleep service initialized", user_id=user_id)

    def _transform_api_record(self, api_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Whoop API sleep record to database format.

        Args:
            api_record: Raw API response record

        Returns:
            Dictionary matching SleepRecord model fields
        """
        # Extract nested score data
        score = api_record.get("score", {})

        return {
            "id": UUID(api_record["id"]),
            "user_id": self.user_id,
            "start_time": datetime.fromisoformat(
                api_record["start"].replace("Z", "+00:00")
            ),
            "end_time": datetime.fromisoformat(
                api_record["end"].replace("Z", "+00:00")
            ),
            "timezone_offset": api_record.get("timezone_offset"),
            "light_sleep_duration": score.get("stage_summary", {}).get(
                "total_light_sleep_time_milli"
            ),
            "slow_wave_sleep_duration": score.get("stage_summary", {}).get(
                "total_slow_wave_sleep_time_milli"
            ),
            "rem_sleep_duration": score.get("stage_summary", {}).get(
                "total_rem_sleep_time_milli"
            ),
            "awake_duration": score.get("stage_summary", {}).get(
                "total_awake_time_milli"
            ),
            "sleep_performance_percentage": score.get("sleep_performance_percentage"),
            "sleep_consistency_percentage": score.get("sleep_consistency_percentage"),
            "respiratory_rate": score.get("respiratory_rate"),
            "sleep_efficiency": score.get("sleep_efficiency_percentage"),
            "score_state": api_record.get("score_state"),
            "is_nap": api_record.get("nap", False),
            "raw_data": api_record,  # Store complete API response
            "updated_at": datetime.now(timezone.utc),
        }

    async def sync_sleep_records(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """
        Sync sleep records from Whoop API to database.

        Fetches records from API and performs upsert (insert or update).
        If no start date provided, fetches from last sync time.

        Args:
            start: Start date for records (uses last sync if None)
            end: End date for records

        Returns:
            Number of records synced
        """
        logger.info(
            "Starting sleep sync",
            user_id=self.user_id,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
        )

        # Get last sync time if no start date provided
        if start is None:
            with get_db_context() as db:
                stmt = (
                    select(SyncStatus)
                    .where(SyncStatus.user_id == self.user_id)
                    .where(SyncStatus.data_type == "sleep")
                )
                sync_status = db.execute(stmt).scalar_one_or_none()

                if sync_status and sync_status.last_record_time:
                    start = sync_status.last_record_time
                    logger.info(
                        "Using last sync time as start",
                        start=start.isoformat(),
                    )

        try:
            # Fetch records from API
            api_records = await self.whoop_client.get_sleep_records(
                start=start,
                end=end,
            )

            if not api_records:
                logger.info("No sleep records to sync", user_id=self.user_id)
                self._update_sync_status(
                    status="success",
                    records_fetched=0,
                    last_sync_time=datetime.now(timezone.utc),
                    last_record_time=start,
                )
                return 0

            # Transform and upsert records
            records_synced = 0

            with get_db_context() as db:
                for api_record in api_records:
                    try:
                        # Transform API record to database format
                        db_record = self._transform_api_record(api_record)

                        # Upsert (insert or update on conflict)
                        stmt = insert(SleepRecord).values(**db_record)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["id"],
                            set_={
                                **db_record,
                                "updated_at": datetime.now(timezone.utc),
                            },
                        )

                        db.execute(stmt)
                        records_synced += 1

                    except Exception as e:
                        logger.error(
                            "Failed to sync sleep record",
                            record_id=api_record.get("id"),
                            error=str(e),
                            exc_info=True,
                        )
                        # Continue with other records

                # Get most recent record time for next sync
                latest_record = max(
                    api_records,
                    key=lambda r: datetime.fromisoformat(
                        r["end"].replace("Z", "+00:00")
                    ),
                )
                latest_time = datetime.fromisoformat(
                    latest_record["end"].replace("Z", "+00:00")
                )

            # Update sync status
            self._update_sync_status(
                status="success",
                records_fetched=records_synced,
                last_sync_time=datetime.now(timezone.utc),
                last_record_time=latest_time,
            )

            logger.info(
                "Sleep sync completed",
                user_id=self.user_id,
                records_synced=records_synced,
            )

            return records_synced

        except Exception as e:
            logger.error(
                "Sleep sync failed",
                user_id=self.user_id,
                error=str(e),
                exc_info=True,
            )

            # Update sync status with error
            self._update_sync_status(
                status="error",
                error_message=str(e),
                last_sync_time=datetime.now(timezone.utc),
            )

            raise

    def _update_sync_status(
        self,
        status: str,
        records_fetched: Optional[int] = None,
        last_sync_time: Optional[datetime] = None,
        last_record_time: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update sync status in database.

        Args:
            status: Sync status ("success" or "error")
            records_fetched: Number of records synced
            last_sync_time: Time of sync
            last_record_time: Timestamp of most recent record
            error_message: Error message if failed
        """
        with get_db_context() as db:
            # Check if sync status exists
            stmt = (
                select(SyncStatus)
                .where(SyncStatus.user_id == self.user_id)
                .where(SyncStatus.data_type == "sleep")
            )
            sync_status = db.execute(stmt).scalar_one_or_none()

            if sync_status:
                # Update existing
                sync_status.status = status
                sync_status.last_sync_time = last_sync_time or datetime.now(
                    timezone.utc
                )

                if records_fetched is not None:
                    sync_status.records_fetched = records_fetched
                if last_record_time:
                    sync_status.last_record_time = last_record_time
                if error_message:
                    sync_status.error_message = error_message
                else:
                    sync_status.error_message = None  # Clear previous errors

                sync_status.updated_at = datetime.now(timezone.utc)

            else:
                # Create new
                sync_status = SyncStatus(
                    user_id=self.user_id,
                    data_type="sleep",
                    status=status,
                    last_sync_time=last_sync_time or datetime.now(timezone.utc),
                    last_record_time=last_record_time,
                    records_fetched=records_fetched,
                    error_message=error_message,
                )
                db.add(sync_status)

            logger.debug(
                "Updated sync status",
                data_type="sleep",
                status=status,
                records_fetched=records_fetched,
            )

    async def get_sleep_statistics(self) -> Dict[str, Any]:
        """
        Get sleep statistics for user.

        Returns:
            Dictionary with sleep stats (count, date range, etc.)
        """
        with get_db_context() as db:
            stmt = select(SleepRecord).where(SleepRecord.user_id == self.user_id)
            records = db.execute(stmt).scalars().all()

            if not records:
                return {
                    "total_records": 0,
                    "date_range": None,
                }

            return {
                "total_records": len(records),
                "earliest_record": min(r.start_time for r in records).isoformat(),
                "latest_record": max(r.end_time for r in records).isoformat(),
                "pending_scores": sum(
                    1 for r in records if r.score_state == "PENDING_SCORE"
                ),
            }
