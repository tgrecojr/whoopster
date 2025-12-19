"""Service for managing workout data from Whoop API.

This module handles fetching workout records from the Whoop API,
transforming them to database models, and performing upsert operations.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.api.whoop_client import WhoopClient
from src.models.db_models import WorkoutRecord, SyncStatus
from src.database.session import get_db_context
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class WorkoutService:
    """
    Service for managing workout data.

    Handles fetching workout records from Whoop API and storing/updating
    them in the database with upsert logic.

    Attributes:
        whoop_client: Whoop API client instance
        user_id: Database user ID
    """

    def __init__(self, user_id: int, whoop_client: WhoopClient) -> None:
        """
        Initialize workout service.

        Args:
            user_id: Database user ID
            whoop_client: Whoop API client instance
        """
        self.user_id = user_id
        self.whoop_client = whoop_client

        logger.info("Workout service initialized", user_id=user_id)

    def _transform_api_record(self, api_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Whoop API workout record to database format.

        Args:
            api_record: Raw API response record

        Returns:
            Dictionary matching WorkoutRecord model fields
        """
        # Extract nested score data
        score = api_record.get("score", {})
        zone_duration = score.get("zone_duration", {})

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
            "sport_id": api_record.get("sport_id"),
            "sport_name": api_record.get("sport_name"),
            "strain_score": score.get("strain"),
            "average_heart_rate": score.get("average_heart_rate"),
            "max_heart_rate": score.get("max_heart_rate"),
            "kilojoules": score.get("kilojoule"),
            "distance_meters": score.get("distance_meter"),
            "altitude_gain_meters": score.get("altitude_gain_meter"),
            "altitude_change_meters": score.get("altitude_change_meter"),
            "zone_zero_duration": zone_duration.get("zone_zero_milli"),
            "zone_one_duration": zone_duration.get("zone_one_milli"),
            "zone_two_duration": zone_duration.get("zone_two_milli"),
            "zone_three_duration": zone_duration.get("zone_three_milli"),
            "zone_four_duration": zone_duration.get("zone_four_milli"),
            "zone_five_duration": zone_duration.get("zone_five_milli"),
            "score_state": api_record.get("score_state"),
            "raw_data": api_record,  # Store complete API response
            "updated_at": datetime.now(timezone.utc),
        }

    async def sync_workout_records(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """
        Sync workout records from Whoop API to database.

        Fetches records from API and performs upsert (insert or update).
        If no start date provided, fetches from last sync time.

        Args:
            start: Start date for records (uses last sync if None)
            end: End date for records

        Returns:
            Number of records synced
        """
        logger.info(
            "Starting workout sync",
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
                    .where(SyncStatus.data_type == "workout")
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
            api_records = await self.whoop_client.get_workout_records(
                start=start,
                end=end,
            )

            if not api_records:
                logger.info("No workout records to sync", user_id=self.user_id)
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
                        stmt = insert(WorkoutRecord).values(**db_record)
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
                            "Failed to sync workout record",
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
                "Workout sync completed",
                user_id=self.user_id,
                records_synced=records_synced,
            )

            return records_synced

        except Exception as e:
            logger.error(
                "Workout sync failed",
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
                .where(SyncStatus.data_type == "workout")
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
                    data_type="workout",
                    status=status,
                    last_sync_time=last_sync_time or datetime.now(timezone.utc),
                    last_record_time=last_record_time,
                    records_fetched=records_fetched,
                    error_message=error_message,
                )
                db.add(sync_status)

            logger.debug(
                "Updated sync status",
                data_type="workout",
                status=status,
                records_fetched=records_fetched,
            )

    async def get_workout_statistics(self) -> Dict[str, Any]:
        """
        Get workout statistics for user.

        Returns:
            Dictionary with workout stats (count, date range, etc.)
        """
        with get_db_context() as db:
            stmt = select(WorkoutRecord).where(WorkoutRecord.user_id == self.user_id)
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
                "unique_sports": len(set(r.sport_name for r in records if r.sport_name)),
            }
