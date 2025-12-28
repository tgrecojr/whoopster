"""Service for managing recovery data from Whoop API.

This module handles fetching recovery records from the Whoop API,
transforming them to database models, and performing upsert operations.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.api.whoop_client import WhoopClient
from src.models.db_models import RecoveryRecord, SyncStatus
from src.database.session import get_db_context
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class RecoveryService:
    """
    Service for managing recovery data.

    Handles fetching recovery records from Whoop API and storing/updating
    them in the database with upsert logic.

    Attributes:
        whoop_client: Whoop API client instance
        user_id: Database user ID
    """

    def __init__(self, user_id: int, whoop_client: WhoopClient) -> None:
        """
        Initialize recovery service.

        Args:
            user_id: Database user ID
            whoop_client: Whoop API client instance
        """
        self.user_id = user_id
        self.whoop_client = whoop_client

        logger.info("Recovery service initialized", user_id=user_id)

    def _transform_api_record(self, api_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Whoop API recovery record to database format.

        Args:
            api_record: Raw API response record

        Returns:
            Dictionary matching RecoveryRecord model fields
        """
        # Extract nested score data
        score = api_record.get("score", {})

        # Note: v2 API doesn't provide a recovery ID - we use DB auto-generated UUID
        # cycle_id in API is integer, but our DB uses UUID - we store API data in raw_data
        return {
            # "id" omitted - let database auto-generate UUID
            "user_id": self.user_id,
            # "cycle_id" omitted - API provides integer, DB expects UUID (stored in raw_data)
            "created_at_whoop": datetime.fromisoformat(
                api_record["created_at"].replace("Z", "+00:00")
            ),
            "recovery_score": score.get("recovery_score"),
            "resting_heart_rate": score.get("resting_heart_rate"),
            "hrv_rmssd": score.get("hrv_rmssd_milli"),
            "spo2_percentage": score.get("spo2_percentage"),
            "skin_temp_celsius": score.get("skin_temp_celsius"),
            "score_state": api_record.get("score_state"),
            "calibrating": score.get("user_calibrating", False),
            "raw_data": api_record,  # Store complete API response (includes integer cycle_id)
            "updated_at": datetime.now(timezone.utc),
        }

    async def sync_recovery_records(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """
        Sync recovery records from Whoop API to database.

        Fetches records from API and performs upsert (insert or update).
        If no start date provided, fetches from last sync time.

        Args:
            start: Start date for records (uses last sync if None)
            end: End date for records

        Returns:
            Number of records synced
        """
        logger.info(
            "Starting recovery sync",
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
                    .where(SyncStatus.data_type == "recovery")
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
            api_records = await self.whoop_client.get_recovery_records(
                start=start,
                end=end,
            )

            if not api_records:
                logger.info("No recovery records to sync", user_id=self.user_id)
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
                for idx, api_record in enumerate(api_records):
                    try:
                        # Log first record for debugging
                        if idx == 0:
                            logger.info(
                                "Sample recovery API record",
                                api_record_keys=list(api_record.keys()),
                                sample_data=api_record,
                            )

                        # Transform API record to database format
                        db_record = self._transform_api_record(api_record)

                        logger.debug(
                            "Inserting recovery record",
                            created_at_whoop=db_record.get("created_at_whoop"),
                            recovery_score=db_record.get("recovery_score"),
                        )

                        # Insert record (no natural unique ID from API, so we can't upsert)
                        # Database will auto-generate UUID for id field
                        stmt = insert(RecoveryRecord).values(**db_record)

                        db.execute(stmt)
                        records_synced += 1

                        logger.debug("Recovery record inserted successfully", index=idx)

                    except Exception as e:
                        logger.error(
                            "Failed to sync recovery record",
                            index=idx,
                            error=str(e),
                            exc_info=True,
                        )
                        # Continue with other records

                # Get most recent record time for next sync
                latest_record = max(
                    api_records,
                    key=lambda r: datetime.fromisoformat(
                        r["created_at"].replace("Z", "+00:00")
                    ),
                )
                latest_time = datetime.fromisoformat(
                    latest_record["created_at"].replace("Z", "+00:00")
                )

            # Update sync status
            self._update_sync_status(
                status="success",
                records_fetched=records_synced,
                last_sync_time=datetime.now(timezone.utc),
                last_record_time=latest_time,
            )

            logger.info(
                "Recovery sync completed",
                user_id=self.user_id,
                records_synced=records_synced,
            )

            return records_synced

        except Exception as e:
            logger.error(
                "Recovery sync failed",
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
                .where(SyncStatus.data_type == "recovery")
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
                    data_type="recovery",
                    status=status,
                    last_sync_time=last_sync_time or datetime.now(timezone.utc),
                    last_record_time=last_record_time,
                    records_fetched=records_fetched,
                    error_message=error_message,
                )
                db.add(sync_status)

            logger.debug(
                "Updated sync status",
                data_type="recovery",
                status=status,
                records_fetched=records_fetched,
            )

    async def get_recovery_statistics(self) -> Dict[str, Any]:
        """
        Get recovery statistics for user.

        Returns:
            Dictionary with recovery stats (count, date range, etc.)
        """
        with get_db_context() as db:
            stmt = select(RecoveryRecord).where(RecoveryRecord.user_id == self.user_id)
            records = db.execute(stmt).scalars().all()

            if not records:
                return {
                    "total_records": 0,
                    "date_range": None,
                }

            return {
                "total_records": len(records),
                "earliest_record": min(r.created_at_whoop for r in records).isoformat(),
                "latest_record": max(r.created_at_whoop for r in records).isoformat(),
                "pending_scores": sum(
                    1 for r in records if r.score_state == "PENDING_SCORE"
                ),
            }
