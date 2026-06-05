"""Tests for windowed reconciliation (overlap window + delete-reconcile).

Covers the two correctness gaps polling can't fix on its own:
* late rescores -> overlap window re-fetch + idempotent upsert (no duplicates)
* Whoop-side deletions -> delete-reconcile drops rows the API no longer returns,
  with guards so settling / pending / out-of-window rows are never touched.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from src.api.whoop_client import WhoopClient
from src.models.db_models import SleepRecord, RecoveryRecord, CycleRecord
from src.services.recovery_service import RecoveryService
from src.services.cycle_service import CycleService
from src.services.reconcile import windowed_start, reconcile_deletes


def _commit_on_exit(db_session):
    """Mimic get_db_context: commit when the `with` block exits."""

    def _exit(*args):
        db_session.commit()
        return None

    return _exit


def _make_sleep(db, user, *, end, score_state="SCORED", row_id=None):
    rec = SleepRecord(
        id=row_id or uuid4(),
        user_id=user.id,
        start_time=end - timedelta(hours=8),
        end_time=end,
        score_state=score_state,
        raw_data={},
    )
    db.add(rec)
    db.commit()
    return rec


# ============================================================================
# windowed_start
# ============================================================================

@pytest.mark.unit
class TestWindowedStart:
    def test_subtracts_window(self):
        t = datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc)
        assert windowed_start(t, window_days=7) == t - timedelta(days=7)

    def test_none_passthrough_preserves_full_backfill(self):
        # First-ever sync has no watermark; must stay None (full backfill), not
        # collapse to an empty/now-anchored window.
        assert windowed_start(None) is None

    def test_uses_configured_window_by_default(self):
        from src.config import settings

        t = datetime(2026, 6, 5, tzinfo=timezone.utc)
        expected = t - timedelta(days=settings.reconcile_window_days)
        assert windowed_start(t) == expected


# ============================================================================
# reconcile_deletes
# ============================================================================

@pytest.mark.unit
class TestReconcileDeletes:
    def test_deletes_in_window_row_absent_from_api(self, db_session, test_user):
        now = datetime.now(timezone.utc)
        keep = _make_sleep(db_session, test_user, end=now - timedelta(days=2))
        drop = _make_sleep(db_session, test_user, end=now - timedelta(days=3))

        deleted = reconcile_deletes(
            db_session,
            SleepRecord,
            user_id=test_user.id,
            time_column=SleepRecord.end_time,
            key_column=SleepRecord.id,
            present_keys={keep.id},  # `drop` is no longer returned by the API
        )
        db_session.commit()

        assert deleted == 1
        ids = {r.id for r in db_session.query(SleepRecord).all()}
        assert keep.id in ids
        assert drop.id not in ids

    def test_guards_protect_recent_pending_and_out_of_window(self, db_session, test_user):
        now = datetime.now(timezone.utc)
        # Too recent (inside the settle margin) -> still settling, keep.
        recent = _make_sleep(db_session, test_user, end=now - timedelta(minutes=10))
        # Pending score -> API may briefly stop returning it; keep.
        pending = _make_sleep(
            db_session, test_user, end=now - timedelta(days=2), score_state="PENDING_SCORE"
        )
        # Older than the reconcile window -> not our concern this poll.
        old = _make_sleep(db_session, test_user, end=now - timedelta(days=30))

        # Empty present_keys = "API returned none of these"; guards must still hold.
        deleted = reconcile_deletes(
            db_session,
            SleepRecord,
            user_id=test_user.id,
            time_column=SleepRecord.end_time,
            key_column=SleepRecord.id,
            present_keys=set(),
        )
        db_session.commit()

        assert deleted == 0
        ids = {r.id for r in db_session.query(SleepRecord).all()}
        assert {recent.id, pending.id, old.id} <= ids

    def test_present_row_is_kept(self, db_session, test_user):
        now = datetime.now(timezone.utc)
        present = _make_sleep(db_session, test_user, end=now - timedelta(days=2))

        deleted = reconcile_deletes(
            db_session,
            SleepRecord,
            user_id=test_user.id,
            time_column=SleepRecord.end_time,
            key_column=SleepRecord.id,
            present_keys={present.id},
        )

        assert deleted == 0
        assert db_session.query(SleepRecord).count() == 1


# ============================================================================
# Service-level idempotency (overlap re-fetch must not duplicate)
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestUpsertIdempotency:
    async def test_recovery_resync_does_not_duplicate(
        self, test_user, db_session, mock_whoop_recovery_response
    ):
        client = WhoopClient(user_id=test_user.id)
        service = RecoveryService(user_id=test_user.id, whoop_client=client)
        records = mock_whoop_recovery_response["records"]

        with patch.object(
            client, "get_recovery_records", new=AsyncMock(return_value=records)
        ):
            with patch("src.services.recovery_service.get_db_context") as mock_ctx:
                mock_ctx.return_value.__enter__.return_value = db_session
                mock_ctx.return_value.__exit__ = _commit_on_exit(db_session)

                await service.sync_recovery_records()
                await service.sync_recovery_records()  # overlap re-fetch

        rows = (
            db_session.query(RecoveryRecord)
            .filter_by(user_id=test_user.id)
            .all()
        )
        assert len(rows) == 1  # upserted on (user_id, cycle_id), not duplicated

    async def test_cycle_resync_does_not_duplicate(
        self, test_user, db_session, mock_whoop_cycle_response
    ):
        client = WhoopClient(user_id=test_user.id)
        service = CycleService(user_id=test_user.id, whoop_client=client)
        records = mock_whoop_cycle_response["records"]

        with patch.object(
            client, "get_cycle_records", new=AsyncMock(return_value=records)
        ):
            with patch("src.services.cycle_service.get_db_context") as mock_ctx:
                mock_ctx.return_value.__enter__.return_value = db_session
                mock_ctx.return_value.__exit__ = _commit_on_exit(db_session)

                await service.sync_cycle_records()
                await service.sync_cycle_records()  # overlap re-fetch

        rows = (
            db_session.query(CycleRecord)
            .filter_by(user_id=test_user.id)
            .all()
        )
        assert len(rows) == 1  # upserted on (user_id, whoop_cycle_id)
