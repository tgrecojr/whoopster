"""Tests for rate limiter."""

import pytest
import asyncio
from collections import deque
from datetime import datetime, timezone, timedelta

from src.api.rate_limiter import RateLimiter


class _PeakDeque(deque):
    """A deque that records the maximum length ever reached."""

    def __init__(self, *args):
        super().__init__(*args)
        self.peak = 0

    def append(self, item):
        super().append(item)
        if len(self) > self.peak:
            self.peak = len(self)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRateLimiter:
    """Tests for RateLimiter class."""

    async def test_rate_limiter_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(max_requests_per_minute=60, safety_margin=0.9)

        assert limiter.max_requests == 54  # 60 * 0.9
        assert limiter.window_seconds == 60
        assert len(limiter.requests) == 0

    async def test_acquire_single_request(self):
        """Test acquiring a single request."""
        limiter = RateLimiter(max_requests_per_minute=60)

        await limiter.acquire()

        assert len(limiter.requests) == 1

    async def test_acquire_multiple_requests(self):
        """Test acquiring multiple requests."""
        limiter = RateLimiter(max_requests_per_minute=60)

        for _ in range(10):
            await limiter.acquire()

        assert len(limiter.requests) == 10

    async def test_rate_limit_not_exceeded(self):
        """Test that rate limit is not exceeded within limit."""
        limiter = RateLimiter(max_requests_per_minute=10)

        start = datetime.now()

        # Acquire 5 requests (below limit of 9 with 0.9 safety margin)
        for _ in range(5):
            await limiter.acquire()

        end = datetime.now()
        duration = (end - start).total_seconds()

        # Should complete quickly (no waiting)
        assert duration < 1.0
        assert len(limiter.requests) == 5

    @pytest.mark.slow
    async def test_rate_limit_enforced(self):
        """Test that rate limit is enforced when exceeded."""
        limiter = RateLimiter(max_requests_per_minute=5, safety_margin=1.0)

        start = datetime.now()

        # Acquire 7 requests (exceeds limit of 5)
        for _ in range(7):
            await limiter.acquire()

        end = datetime.now()
        duration = (end - start).total_seconds()

        # Should have waited significantly (rate limited)
        # With 5 requests per minute, acquiring 7 requests requires waiting for window to clear
        # After the wait, old requests are cleaned up, so we should have <= max_requests
        assert duration > 30  # Had to wait for the window to pass
        assert len(limiter.requests) <= limiter.max_requests  # Old requests cleaned up

    async def test_get_stats(self):
        """Test getting rate limiter statistics."""
        limiter = RateLimiter(max_requests_per_minute=60)

        # Acquire some requests
        for _ in range(10):
            await limiter.acquire()

        stats = await limiter.get_stats()

        assert stats["requests_in_window"] == 10
        assert stats["max_requests"] == 54  # 60 * 0.9
        assert stats["window_seconds"] == 60
        assert stats["available_slots"] == 44
        assert stats["utilization_percent"] == pytest.approx(18.52, abs=0.1)

    async def test_reset(self):
        """Test resetting the rate limiter."""
        limiter = RateLimiter(max_requests_per_minute=60)

        # Acquire some requests
        for _ in range(10):
            await limiter.acquire()

        assert len(limiter.requests) == 10

        # Reset
        await limiter.reset()

        assert len(limiter.requests) == 0

    async def test_cleanup_old_requests(self):
        """Test that old requests are cleaned up."""
        limiter = RateLimiter(max_requests_per_minute=60)

        # Manually add old requests
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=70)

        limiter.requests.append(old_time)
        limiter.requests.append(old_time)
        limiter.requests.append(now)

        # Acquire a new request (triggers cleanup)
        await limiter.acquire()

        # Old requests should be removed
        assert len(limiter.requests) == 2  # Only the recent ones

    async def test_concurrent_requests(self):
        """Test concurrent request handling."""
        limiter = RateLimiter(max_requests_per_minute=20)

        async def make_request():
            await limiter.acquire()

        # Create 15 concurrent requests
        tasks = [make_request() for _ in range(15)]
        await asyncio.gather(*tasks)

        stats = await limiter.get_stats()
        assert stats["requests_in_window"] == 15

    async def test_never_overshoots_max_under_concurrency(self):
        """Concurrent acquirers must never push the window past max_requests.

        The old code used an `if` (not a loop) and released/re-acquired the lock
        by hand, so several waiters could wake and all append at once, exceeding
        the limit. With a short window this reproduces quickly; the recorded
        peak length must stay within max_requests.
        """
        limiter = RateLimiter(max_requests_per_minute=2, safety_margin=1.0)
        assert limiter.max_requests == 2
        limiter.window_seconds = 1  # shrink the window so waits are sub-second
        limiter.requests = _PeakDeque()

        now = datetime.now(timezone.utc)
        # Fill to the limit with entries that are still inside the 1s window.
        limiter.requests.append(now - timedelta(seconds=0.9))
        limiter.requests.append(now - timedelta(seconds=0.1))

        # Three concurrent acquirers contend for slots as the old entries expire.
        await asyncio.gather(*[limiter.acquire() for _ in range(3)])

        assert limiter.requests.peak <= limiter.max_requests
        assert len(limiter.requests) <= limiter.max_requests

    async def test_max_requests_floors_to_at_least_one(self):
        """A tiny config must not floor max_requests to 0 (infinite loop / div0)."""
        limiter = RateLimiter(max_requests_per_minute=1, safety_margin=0.1)
        assert limiter.max_requests == 1  # int(0.1) == 0, clamped up to 1

    async def test_custom_safety_margin(self):
        """Test custom safety margin."""
        limiter = RateLimiter(max_requests_per_minute=100, safety_margin=0.5)

        assert limiter.max_requests == 50  # 100 * 0.5

    async def test_repr(self):
        """Test string representation."""
        limiter = RateLimiter(max_requests_per_minute=60)

        repr_str = repr(limiter)

        assert "RateLimiter" in repr_str
        assert "max_requests=54" in repr_str
        assert "window_seconds=60" in repr_str
