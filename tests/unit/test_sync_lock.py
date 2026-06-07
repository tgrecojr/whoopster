"""Tests for the cross-process advisory sync lock and poller participation."""

import pytest

from src.config import settings
from src.utils.sync_lock import SyncLockTimeout, sync_lock


@pytest.mark.unit
class TestSyncLock:
    """Tests for src.utils.sync_lock.sync_lock."""

    def test_nonblocking_acquires_when_free(self, tmp_path):
        lock_path = str(tmp_path / "lock")
        with sync_lock(blocking=False, path=lock_path) as acquired:
            assert acquired is True

    def test_nonblocking_busy_when_held(self, tmp_path):
        lock_path = str(tmp_path / "lock")
        # A distinct open file description conflicts even within one process,
        # so the inner non-blocking attempt must report busy.
        with sync_lock(blocking=False, path=lock_path) as outer:
            assert outer is True
            with sync_lock(blocking=False, path=lock_path) as inner:
                assert inner is False

    def test_lock_released_on_exit(self, tmp_path):
        lock_path = str(tmp_path / "lock")
        with sync_lock(blocking=False, path=lock_path) as first:
            assert first is True
        # Once the context exits the lock is free again.
        with sync_lock(blocking=False, path=lock_path) as second:
            assert second is True

    def test_blocking_times_out_when_held(self, tmp_path):
        lock_path = str(tmp_path / "lock")
        with sync_lock(blocking=False, path=lock_path) as outer:
            assert outer is True
            with pytest.raises(SyncLockTimeout):
                with sync_lock(
                    blocking=True, timeout=1, path=lock_path, poll_interval=0.05
                ):
                    pass

    def test_blocking_acquires_after_release(self, tmp_path):
        lock_path = str(tmp_path / "lock")
        with sync_lock(blocking=False, path=lock_path):
            pass
        with sync_lock(
            blocking=True, timeout=1, path=lock_path, poll_interval=0.05
        ) as acquired:
            assert acquired is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestPollerLockParticipation:
    """sync_user_data must skip a cycle when the lock is already held."""

    async def test_skips_when_lock_held(self, tmp_path, monkeypatch):
        lock_path = str(tmp_path / "lock")
        monkeypatch.setattr(settings, "sync_lock_path", lock_path)

        from src.services import data_collector as dc

        # The poller must not even construct a collector when it can't get the lock.
        def _boom(*args, **kwargs):
            raise AssertionError("DataCollector should not run while lock is held")

        monkeypatch.setattr(dc, "DataCollector", _boom)

        with sync_lock(blocking=False, path=lock_path) as held:
            assert held is True
            result = await dc.sync_user_data(1)

        assert result["skipped"] is True
        assert result["reason"] == "sync_lock_held"
        assert result["user_id"] == 1
