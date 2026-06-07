"""Cross-process serialization of Whoop API work via an advisory file lock.

The app runs a long-lived poller and, occasionally, a ``docker exec`` backfill
in the SAME container. Both call the rate-limited Whoop API, and each process
keeps its OWN in-memory rate limiter -- so running them at once could exceed the
API limit. We coordinate with a POSIX advisory lock (:func:`fcntl.flock`) on a
shared file so only ONE process talks to the API at a time:

* the poller takes the lock **non-blocking** and SKIPS its cycle if a backfill
  holds it (it catches up on the next interval);
* the backfill takes the lock **blocking** (bounded by a timeout) and runs to
  completion while the poller skips.

``flock`` is released automatically by the kernel when the holding process exits
-- even on a crash or ``kill -9`` -- so there is no stale lock to clean up and
no TTL to tune.
"""

import errno
import fcntl
import os
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from src.config import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class SyncLockTimeout(Exception):
    """Raised when a blocking lock acquisition exceeds its timeout."""


def _try_acquire(fd: int) -> bool:
    """Attempt a single non-blocking exclusive lock. True if acquired."""
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        # Lock held by someone else -> not an error, just "busy".
        if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
            return False
        raise


def _acquire_blocking(fd: int, timeout: int, poll_interval: float, path: str) -> None:
    """Retry the non-blocking lock until acquired or the timeout elapses."""
    deadline = time.monotonic() + max(0, timeout)
    while not _try_acquire(fd):
        if time.monotonic() >= deadline:
            raise SyncLockTimeout(
                f"could not acquire sync lock at {path} within {timeout}s"
            )
        time.sleep(poll_interval)


@contextmanager
def sync_lock(
    *,
    blocking: bool,
    timeout: Optional[int] = None,
    path: Optional[str] = None,
    poll_interval: float = 1.0,
) -> Iterator[bool]:
    """Hold the shared Whoop-sync advisory lock for the duration of the context.

    Args:
        blocking: If True, wait (up to ``timeout`` seconds) for the lock. If
            False, attempt once and yield immediately whether or not it was
            acquired.
        timeout: Max seconds to wait when ``blocking`` (defaults to
            ``settings.sync_lock_timeout_seconds``). Ignored when non-blocking.
        path: Lock file path (defaults to ``settings.sync_lock_path``).
        poll_interval: Seconds between blocking retries.

    Yields:
        ``True`` if the lock is held inside the context, ``False`` otherwise
        (only possible in non-blocking mode).

    Raises:
        SyncLockTimeout: In blocking mode, if the lock can't be acquired within
            ``timeout`` seconds.
    """
    lock_path = path or settings.sync_lock_path
    wait = settings.sync_lock_timeout_seconds if timeout is None else timeout

    # The lock travels with the open file description, not the path, so we keep
    # the fd open for the whole context and closing it releases the lock.
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    acquired = False
    try:
        if blocking:
            _acquire_blocking(fd, wait, poll_interval, lock_path)
            acquired = True
        else:
            acquired = _try_acquire(fd)
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:  # best-effort; closing the fd releases it anyway
                pass
        os.close(fd)
