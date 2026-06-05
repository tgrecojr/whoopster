"""Service for managing recovery data from Whoop API.

This module handles fetching recovery records from the Whoop API,
transforming them to database models, and performing upsert operations.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.api.whoop_client import WhoopClient
from src.models.db_models import RecoveryRecord, SyncStatus
from src.database.session import get_db_context
from src.services.reconcile import windowed_start, reconcile_deletes
from src.services.sync_status import upsert_sync_status
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

        # Note: v2 API doesn't provide a recovery ID - we use DB auto-generated UUID.
        # cycle_id is the Whoop integer cycle id; sleep_id is the UUID of the sleep
        # record this recovery is derived from (joins to sleep_records.id).
        sleep_id = api_record.get("sleep_id")
        return {
            # "id" omitted - let database auto-generate UUID
            "user_id": self.user_id,
            "cycle_id": api_record.get("cycle_id"),
            "sleep_id": UUID(sleep_id) if sleep_id else None,
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
                    # Re-fetch a trailing overlap window so late rescores upsert.
                    start = windowed_start(sync_status.last_record_time)
                    logger.info(
                        "Using last sync time as start (overlap window applied)",
                        start=start.isoformat(),
                        watermark=sync_status.last_record_time.isoformat(),
                    )

        try:
            # Fetch records from API
            api_records = await self.whoop_client.get_recovery_records(
                start=start,
                end=end,
            )

            if not api_records:
                logger.info("No recovery records to sync", user_id=self.user_id)
                # Leave the watermark untouched on an empty fetch (see sleep
                # service): writing the backdated `start` would regress it.
                self._update_sync_status(
                    status="success",
                    records_fetched=0,
                    last_sync_time=datetime.now(timezone.utc),
                    last_record_time=None,
                )
                return 0

            # Transform and upsert records
            records_synced = 0

            with get_db_context() as db:
                for idx, api_record in enumerate(api_records):
                    try:
                        # Log only field names (no health values/PII) at debug.
                        if idx == 0:
                            logger.debug(
                                "Recovery API record fields",
                                api_record_keys=list(api_record.keys()),
                            )

                        # Transform API record to database format
                        db_record = self._transform_api_record(api_record)

                        logger.debug(
                            "Inserting recovery record",
                            created_at_whoop=db_record.get("created_at_whoop"),
                            recovery_score=db_record.get("recovery_score"),
                        )

                        # Upsert on the natural key (user_id, cycle_id). The API
                        # gives no recovery id, but recovery is 1:1 with a cycle,
                        # so re-fetched/rescored recoveries update in place instead
                        # of inserting duplicates. id is omitted (DB-generated UUID
                        # is preserved on conflict).
                        stmt = insert(RecoveryRecord).values(**db_record)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["user_id", "cycle_id"],
                            set_={
                                **db_record,
                                "updated_at": datetime.now(timezone.utc),
                            },
                        )

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

                # Reconcile deletions: drop rows in the window the API no longer
                # returns (a recovery deleted/rescored-away in the Whoop app).
                # Keyed on cycle_id (recovery is 1:1 with a cycle; the API gives no
                # recovery id). Skipped when api_records is empty (handled above).
                present_keys = {
                    r.get("cycle_id")
                    for r in api_records
                    if r.get("cycle_id") is not None
                }
                reconcile_deletes(
                    db,
                    RecoveryRecord,
                    user_id=self.user_id,
                    time_column=RecoveryRecord.created_at_whoop,
                    key_column=RecoveryRecord.cycle_id,
                    present_keys=present_keys,
                    fetch_start=start,
                    fetch_end=end,
                )

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
            upsert_sync_status(
                db,
                user_id=self.user_id,
                data_type="recovery",
                status=status,
                records_fetched=records_fetched,
                last_sync_time=last_sync_time,
                last_record_time=last_record_time,
                error_message=error_message,
            )

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
