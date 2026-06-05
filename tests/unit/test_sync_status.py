"""Tests for the shared sync_status upsert + the (user_id, data_type) constraint."""

import pytest
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from src.models.db_models import SyncStatus
from src.services.sync_status import upsert_sync_status


def _utc(dt):
    """Normalize a possibly-naive stored datetime to tz-aware UTC for comparison."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@pytest.mark.unit
class TestSyncStatusConstraint:
    def test_duplicate_user_datatype_rejected(self, db_session, test_user):
        db_session.add(
            SyncStatus(user_id=test_user.id, data_type="sleep", status="success")
        )
        db_session.commit()

        db_session.add(
            SyncStatus(user_id=test_user.id, data_type="sleep", status="success")
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


@pytest.mark.unit
class TestUpsertSyncStatus:
    def test_inserts_then_updates_in_place(self, db_session, test_user):
        wm1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        wm2 = datetime(2026, 2, 1, tzinfo=timezone.utc)

        upsert_sync_status(
            db_session,
            user_id=test_user.id,
            data_type="sleep",
            status="success",
            records_fetched=3,
            last_record_time=wm1,
        )
        db_session.commit()
        upsert_sync_status(
            db_session,
            user_id=test_user.id,
            data_type="sleep",
            status="success",
            records_fetched=5,
            last_record_time=wm2,
        )
        db_session.commit()

        rows = (
            db_session.query(SyncStatus)
            .filter_by(user_id=test_user.id, data_type="sleep")
            .all()
        )
        assert len(rows) == 1  # upserted, not duplicated
        assert rows[0].records_fetched == 5
        assert _utc(rows[0].last_record_time) == wm2

    def test_preserves_watermark_and_count_when_none(self, db_session, test_user):
        wm = datetime(2026, 1, 1, tzinfo=timezone.utc)
        upsert_sync_status(
            db_session,
            user_id=test_user.id,
            data_type="sleep",
            status="success",
            records_fetched=3,
            last_record_time=wm,
        )
        db_session.commit()

        # Error-path style call: no watermark, no count supplied.
        upsert_sync_status(
            db_session,
            user_id=test_user.id,
            data_type="sleep",
            status="error",
            error_message="boom",
            last_record_time=None,
            records_fetched=None,
        )
        db_session.commit()

        row = (
            db_session.query(SyncStatus)
            .filter_by(user_id=test_user.id, data_type="sleep")
            .one()
        )
        assert row.status == "error"
        assert row.error_message == "boom"
        assert _utc(row.last_record_time) == wm  # preserved, not clobbered
        assert row.records_fetched == 3  # preserved

    def test_clears_error_on_success(self, db_session, test_user):
        upsert_sync_status(
            db_session,
            user_id=test_user.id,
            data_type="sleep",
            status="error",
            error_message="boom",
        )
        db_session.commit()

        upsert_sync_status(
            db_session,
            user_id=test_user.id,
            data_type="sleep",
            status="success",
        )
        db_session.commit()

        row = (
            db_session.query(SyncStatus)
            .filter_by(user_id=test_user.id, data_type="sleep")
            .one()
        )
        assert row.status == "success"
        assert row.error_message is None
