"""Shared upsert for the per-(user, data_type) sync watermark row.

All data services record their progress in a single ``sync_status`` row keyed
by ``(user_id, data_type)``. Writing it via ``on_conflict_do_update`` (rather
than select-then-insert) makes the write atomic, so two overlapping syncs for
the same user/data_type can't both insert and create duplicate rows.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.models.db_models import SyncStatus


def upsert_sync_status(
    db: Session,
    *,
    user_id: int,
    data_type: str,
    status: str,
    records_fetched: Optional[int] = None,
    last_sync_time: Optional[datetime] = None,
    last_record_time: Optional[datetime] = None,
    error_message: Optional[str] = None,
) -> None:
    """Insert or update the sync_status row for one (user_id, data_type).

    ``records_fetched`` and ``last_record_time`` are only written when provided;
    passing ``None`` leaves the existing value untouched (so an error path or an
    empty fetch never clobbers the watermark). ``error_message`` is always set —
    to its value on failure, or cleared to ``None`` on success.
    """
    now = datetime.now(timezone.utc)
    last_sync_time = last_sync_time or now

    insert_values = {
        "user_id": user_id,
        "data_type": data_type,
        "status": status,
        "last_sync_time": last_sync_time,
        "last_record_time": last_record_time,
        "records_fetched": records_fetched,
        "error_message": error_message,
        "updated_at": now,
    }

    update_set = {
        "status": status,
        "last_sync_time": last_sync_time,
        "error_message": error_message,
        "updated_at": now,
    }
    # Preserve existing values when the caller didn't supply a new one.
    if records_fetched is not None:
        update_set["records_fetched"] = records_fetched
    if last_record_time is not None:
        update_set["last_record_time"] = last_record_time

    stmt = insert(SyncStatus).values(**insert_values).on_conflict_do_update(
        index_elements=["user_id", "data_type"],
        set_=update_set,
    )
    db.execute(stmt)
