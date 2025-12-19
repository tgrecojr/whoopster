"""Rate limiter for Whoop API requests.

This module implements a sliding window rate limiter to ensure compliance
with Whoop API rate limits (60 requests per minute).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Optional

from src.config import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter for API requests.

    Tracks request timestamps and enforces rate limits by delaying
    requests when necessary. Thread-safe for concurrent operations.

    Attributes:
        max_requests: Maximum requests allowed per window
        window_seconds: Time window in seconds
        requests: Deque of request timestamps
        lock: Asyncio lock for thread safety
    """

    def __init__(
        self,
        max_requests_per_minute: Optional[int] = None,
        safety_margin: float = 0.9,
    ) -> None:
        """
        Initialize rate limiter.

        Args:
            max_requests_per_minute: Maximum requests per minute (from settings if None)
            safety_margin: Multiplier for max requests (0.9 = 90% of limit for safety)
        """
        self.max_requests = int(
            (max_requests_per_minute or settings.max_requests_per_minute) * safety_margin
        )
        self.window_seconds = 60  # 1 minute window
        self.requests: deque[datetime] = deque()
        self.lock = asyncio.Lock()

        logger.info(
            "Rate limiter initialized",
            max_requests=self.max_requests,
            window_seconds=self.window_seconds,
            safety_margin=safety_margin,
        )

    async def acquire(self) -> None:
        """
        Acquire permission to make an API request.

        Blocks if rate limit would be exceeded, waiting until a request
        slot becomes available.

        This method should be called before every API request.
        """
        async with self.lock:
            now = datetime.now(timezone.utc)

            # Remove timestamps outside the current window
            self._cleanup_old_requests(now)

            # Check if we're at the limit
            if len(self.requests) >= self.max_requests:
                # Calculate how long to wait
                oldest_request = self.requests[0]
                window_start = now - timedelta(seconds=self.window_seconds)

                if oldest_request > window_start:
                    # We're at the limit, need to wait
                    wait_time = (
                        oldest_request - window_start
                    ).total_seconds() + 0.1  # Add small buffer

                    logger.warning(
                        "Rate limit reached, waiting",
                        wait_seconds=wait_time,
                        requests_in_window=len(self.requests),
                        max_requests=self.max_requests,
                    )

                    # Release lock while waiting
                    self.lock.release()
                    try:
                        await asyncio.sleep(wait_time)
                    finally:
                        await self.lock.acquire()

                    # Re-clean after waiting
                    now = datetime.now(timezone.utc)
                    self._cleanup_old_requests(now)

            # Record this request
            self.requests.append(now)

            logger.debug(
                "Rate limit acquired",
                requests_in_window=len(self.requests),
                max_requests=self.max_requests,
                utilization_percent=(len(self.requests) / self.max_requests) * 100,
            )

    def _cleanup_old_requests(self, now: datetime) -> None:
        """
        Remove request timestamps outside the current window.

        Args:
            now: Current timestamp
        """
        window_start = now - timedelta(seconds=self.window_seconds)

        while self.requests and self.requests[0] < window_start:
            self.requests.popleft()

    async def get_stats(self) -> dict:
        """
        Get current rate limiter statistics.

        Returns:
            Dictionary with rate limiter stats
        """
        async with self.lock:
            now = datetime.now(timezone.utc)
            self._cleanup_old_requests(now)

            return {
                "requests_in_window": len(self.requests),
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "utilization_percent": (len(self.requests) / self.max_requests) * 100,
                "available_slots": self.max_requests - len(self.requests),
            }

    async def reset(self) -> None:
        """Reset the rate limiter (clear all tracked requests)."""
        async with self.lock:
            self.requests.clear()
            logger.info("Rate limiter reset")

    def __repr__(self) -> str:
        """String representation of rate limiter."""
        return (
            f"RateLimiter(max_requests={self.max_requests}, "
            f"window_seconds={self.window_seconds}, "
            f"current_requests={len(self.requests)})"
        )


class RateLimitExceeded(Exception):
    """
    Exception raised when rate limit is exceeded.

    This is generally not raised in normal operation since the rate limiter
    will automatically wait. It's provided for testing and edge cases.
    """

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float = 60.0):
        """
        Initialize exception.

        Args:
            message: Error message
            retry_after: Seconds to wait before retrying
        """
        self.retry_after = retry_after
        super().__init__(f"{message} (retry after {retry_after}s)")
