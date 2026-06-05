"""Shared helpers for windowed reconciliation of polled Whoop data.

Polling alone can't observe two things, because every service upserts and never
deletes, and advances a watermark past records once seen:

* **Deletions** made in the Whoop app leave a stale row in our DB forever.
* **Late rescores** of a record older than the watermark are never re-fetched.

Both are fixed by re-fetching a trailing window on each poll and reconciling it
against the database:

* :func:`windowed_start` shifts the watermark back by the overlap window so the
  list fetch re-includes recently-changed records (they then upsert in place).
* :func:`reconcile_deletes` drops local rows inside the window that the API no
  longer returns.

The window/margin come from settings (``reconcile_window_days``,
``reconcile_settle_minutes``).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Set

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.orm import InstrumentedAttribute, Session

from src.config import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to tz-aware UTC so window comparisons are safe."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def windowed_start(
    last_record_time: Optional[datetime],
    window_days: Optional[int] = None,
) -> Optional[datetime]:
    """Shift a sync watermark back by the overlap window.

    Re-fetching the trailing window lets rescored/late-finalized records upsert
    in place. ``None`` is returned unchanged so a first-ever sync still does a
    full backfill rather than an empty window.

    Args:
        last_record_time: The stored watermark (max record time), or None.
        window_days: Override the configured window (mainly for tests).

    Returns:
        The watermark minus the window, or None if no watermark exists.
    """
    if last_record_time is None:
        return None
    days = settings.reconcile_window_days if window_days is None else window_days
    return last_record_time - timedelta(days=days)


def reconcile_deletes(
    db: Session,
    model: Any,
    *,
    user_id: int,
    time_column: InstrumentedAttribute,
    key_column: InstrumentedAttribute,
    present_keys: Set[Any],
    window_days: Optional[int] = None,
    settle_margin: Optional[timedelta] = None,
    fetch_start: Optional[datetime] = None,
    fetch_end: Optional[datetime] = None,
    skip_score_states: Iterable[str] = ("PENDING_SCORE",),
) -> int:
    """Delete local rows in the reconcile window the API no longer returns.

    Only ever call this with the keys from a **non-empty** fetch — an empty fetch
    (e.g. a transient API blip) must not be read as "everything was deleted".

    A row is deleted only when ALL of the following hold, so we never drop a
    record that is merely settling or sitting just outside the fetched window:

      * its natural key is non-null and absent from ``present_keys``;
      * its ``time_column`` is within ``[now - window, now - settle_margin]``,
        further clamped to the actually-fetched ``[fetch_start, fetch_end]`` so a
        bounded/backfill fetch is never treated as authoritative beyond its range;
      * its ``score_state`` (if the model has one) is not still pending.

    Args:
        db: Active session (same transaction as the surrounding sync).
        model: The ORM model class to reconcile.
        user_id: Restrict to this user's rows.
        time_column: Timestamp column defining the window (e.g. ``end_time``).
        key_column: Natural-key column compared against ``present_keys``.
        present_keys: Keys present in the API response for this poll.
        window_days: Override the configured window (mainly for tests).
        settle_margin: Override the configured settle margin (mainly for tests).
        fetch_start: Lower bound actually sent to the API (the windowed start).
            Rows below it weren't requested, so the window is clamped up to it.
        fetch_end: Upper bound actually sent to the API, if any. Rows above it
            weren't requested, so the cutoff is clamped down to it.
        skip_score_states: score_state values that keep a row regardless.

    Returns:
        Number of rows deleted.
    """
    now = datetime.now(timezone.utc)
    days = settings.reconcile_window_days if window_days is None else window_days
    window_start = now - timedelta(days=days)
    if settle_margin is None:
        settle_margin = timedelta(minutes=settings.reconcile_settle_minutes)
    cutoff = now - settle_margin

    # Clamp the reconcile window to what was actually fetched. Without this, an
    # explicit `end` (or a `start` newer than the default window) would let us
    # delete rows in a range the API was never asked about.
    fetch_start = _as_utc(fetch_start)
    fetch_end = _as_utc(fetch_end)
    if fetch_start is not None and fetch_start > window_start:
        window_start = fetch_start
    if fetch_end is not None and fetch_end < cutoff:
        cutoff = fetch_end
    if window_start > cutoff:
        return 0

    stmt = select(model).where(
        model.user_id == user_id,
        time_column >= window_start,
        time_column <= cutoff,
    )

    has_score_state = hasattr(model, "score_state")
    skip = set(skip_score_states)
    key_attr = key_column.key

    to_delete = []
    for row in db.execute(stmt).scalars():
        if has_score_state and row.score_state in skip:
            continue
        key_value = getattr(row, key_attr)
        # A null natural key can never match the API response, so it would always
        # look "deleted". Keep it rather than dropping a row we can't reconcile.
        if key_value is None or key_value in present_keys:
            continue
        to_delete.append(row.id)

    if not to_delete:
        return 0

    db.execute(sa_delete(model).where(model.id.in_(to_delete)))
    logger.info(
        "Reconciled deletions from Whoop",
        model=model.__tablename__,
        user_id=user_id,
        deleted=len(to_delete),
    )
    return len(to_delete)
