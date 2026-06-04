"""Service for managing body measurement data from Whoop API.

The Whoop API only returns the *current* body measurement (height, weight,
max heart rate) with no history. This service stores it as a time-series:
a new row is written only when a value differs from the most recent stored
row, so weight/height changes accumulate going forward without daily duplicates.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy import select

from src.api.whoop_client import WhoopClient, WhoopAPIError
from src.models.db_models import BodyMeasurement, SyncStatus
from src.database.session import get_db_context
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# HTTP statuses meaning "token can't read this" (e.g. read:body_measurement
# scope not yet granted). Handled as a graceful skip rather than an error.
_UNAUTHORIZED_STATUSES = (401, 403)


def _to_decimal(value: Any, places: str = "0.001") -> Optional[Decimal]:
    """Normalize an API numeric value to a fixed-precision Decimal.

    Quantizing to the column's precision keeps change-detection stable (the
    stored value and a freshly-fetched value compare equal when unchanged).
    """
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(places))


class BodyMeasurementService:
    """Service for managing body measurement data."""

    def __init__(self, user_id: int, whoop_client: WhoopClient) -> None:
        """
        Initialize body measurement service.

        Args:
            user_id: Database user ID
            whoop_client: Whoop API client instance
        """
        self.user_id = user_id
        self.whoop_client = whoop_client

        logger.info("Body measurement service initialized", user_id=user_id)

    def _transform_api_record(self, api_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Whoop API body measurement to database format.

        Args:
            api_record: Raw API response

        Returns:
            Dictionary matching BodyMeasurement model fields (excluding recorded_at)
        """
        return {
            "user_id": self.user_id,
            "height_meter": _to_decimal(api_record.get("height_meter")),
            "weight_kilogram": _to_decimal(api_record.get("weight_kilogram")),
            "max_heart_rate": api_record.get("max_heart_rate"),
            "raw_data": api_record,
        }

    @staticmethod
    def _is_changed(latest: Optional[BodyMeasurement], candidate: Dict[str, Any]) -> bool:
        """Return True if candidate differs from the latest stored row (or none exists)."""
        if latest is None:
            return True
        return (
            latest.height_meter != candidate["height_meter"]
            or latest.weight_kilogram != candidate["weight_kilogram"]
            or latest.max_heart_rate != candidate["max_heart_rate"]
        )

    async def sync_body_measurement(self) -> int:
        """
        Sync the current body measurement from Whoop API.

        Inserts a new time-series row only when a value has changed since the
        last stored snapshot. If the token lacks the read:body_measurement
        scope (401/403), the sync is skipped gracefully (not treated as an
        error) so it auto-activates once the scope is granted.

        Returns:
            Number of records inserted (0 or 1)
        """
        logger.info("Starting body measurement sync", user_id=self.user_id)

        try:
            api_record = await self.whoop_client.get_body_measurement()
        except WhoopAPIError as e:
            if e.status_code in _UNAUTHORIZED_STATUSES:
                logger.info(
                    "Skipping body measurement sync; read:body_measurement scope "
                    "not granted (re-authorize to enable)",
                    user_id=self.user_id,
                    status_code=e.status_code,
                )
                self._update_sync_status(
                    status="skipped",
                    records_fetched=0,
                    last_sync_time=datetime.now(timezone.utc),
                )
                return 0
            logger.error(
                "Body measurement sync failed",
                user_id=self.user_id,
                status_code=e.status_code,
                error=str(e),
                exc_info=True,
            )
            self._update_sync_status(
                status="error",
                error_message=str(e),
                last_sync_time=datetime.now(timezone.utc),
            )
            raise

        candidate = self._transform_api_record(api_record)

        try:
            inserted = 0
            now = datetime.now(timezone.utc)

            with get_db_context() as db:
                stmt = (
                    select(BodyMeasurement)
                    .where(BodyMeasurement.user_id == self.user_id)
                    .order_by(BodyMeasurement.recorded_at.desc())
                )
                latest = db.execute(stmt).scalars().first()

                if self._is_changed(latest, candidate):
                    db.add(BodyMeasurement(recorded_at=now, **candidate))
                    inserted = 1
                    logger.info(
                        "Inserted body measurement snapshot",
                        user_id=self.user_id,
                        weight_kilogram=str(candidate["weight_kilogram"]),
                        max_heart_rate=candidate["max_heart_rate"],
                    )
                else:
                    logger.info(
                        "Body measurement unchanged; no new snapshot",
                        user_id=self.user_id,
                    )

            self._update_sync_status(
                status="success",
                records_fetched=inserted,
                last_sync_time=now,
                last_record_time=now,
            )

            logger.info(
                "Body measurement sync completed",
                user_id=self.user_id,
                records_synced=inserted,
            )

            return inserted

        except Exception as e:
            logger.error(
                "Body measurement sync failed",
                user_id=self.user_id,
                error=str(e),
                exc_info=True,
            )
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
        """Update sync status row for the body_measurement data type."""
        with get_db_context() as db:
            stmt = (
                select(SyncStatus)
                .where(SyncStatus.user_id == self.user_id)
                .where(SyncStatus.data_type == "body_measurement")
            )
            sync_status = db.execute(stmt).scalar_one_or_none()

            if sync_status:
                sync_status.status = status
                sync_status.last_sync_time = last_sync_time or datetime.now(timezone.utc)

                if records_fetched is not None:
                    sync_status.records_fetched = records_fetched
                if last_record_time:
                    sync_status.last_record_time = last_record_time
                if error_message:
                    sync_status.error_message = error_message
                else:
                    sync_status.error_message = None

                sync_status.updated_at = datetime.now(timezone.utc)
            else:
                sync_status = SyncStatus(
                    user_id=self.user_id,
                    data_type="body_measurement",
                    status=status,
                    last_sync_time=last_sync_time or datetime.now(timezone.utc),
                    last_record_time=last_record_time,
                    records_fetched=records_fetched,
                    error_message=error_message,
                )
                db.add(sync_status)

            logger.debug(
                "Updated sync status",
                data_type="body_measurement",
                status=status,
                records_fetched=records_fetched,
            )

    async def get_body_measurement_statistics(self) -> Dict[str, Any]:
        """
        Get body measurement statistics for user.

        Returns:
            Dictionary with snapshot count and the latest measurement.
        """
        with get_db_context() as db:
            stmt = (
                select(BodyMeasurement)
                .where(BodyMeasurement.user_id == self.user_id)
                .order_by(BodyMeasurement.recorded_at.desc())
            )
            records = db.execute(stmt).scalars().all()

            if not records:
                return {"total_records": 0, "latest": None}

            latest = records[0]
            return {
                "total_records": len(records),
                "latest": {
                    "height_meter": (
                        float(latest.height_meter)
                        if latest.height_meter is not None
                        else None
                    ),
                    "weight_kilogram": (
                        float(latest.weight_kilogram)
                        if latest.weight_kilogram is not None
                        else None
                    ),
                    "max_heart_rate": latest.max_heart_rate,
                    "recorded_at": latest.recorded_at.isoformat(),
                },
            }
