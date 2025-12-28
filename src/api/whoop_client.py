"""Whoop API client for fetching user data.

This module implements a comprehensive client for the Whoop API v2,
supporting sleep, workout, recovery, and cycle data with pagination,
rate limiting, and automatic token refresh.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, AsyncIterator
from urllib.parse import urlencode

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import settings
from src.auth.token_manager import TokenManager
from src.api.rate_limiter import RateLimiter
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class WhoopAPIError(Exception):
    """Base exception for Whoop API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.status_code = status_code
        super().__init__(message)


class WhoopClient:
    """
    Client for Whoop API v2.

    Provides methods to fetch sleep, workout, recovery, and cycle data
    with automatic pagination, rate limiting, and error handling.

    Attributes:
        user_id: Database user ID
        token_manager: Token manager for authentication
        rate_limiter: Rate limiter for API requests
        base_url: Whoop API base URL
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        user_id: int,
        token_manager: Optional[TokenManager] = None,
        rate_limiter: Optional[RateLimiter] = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize Whoop API client.

        Args:
            user_id: Database user ID for token retrieval
            token_manager: Token manager instance (creates new if None)
            rate_limiter: Rate limiter instance (creates new if None)
            timeout: Request timeout in seconds
        """
        self.user_id = user_id
        self.token_manager = token_manager or TokenManager()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.base_url = settings.whoop_api_base_url
        self.timeout = timeout

        logger.info(
            "Whoop client initialized",
            user_id=user_id,
            base_url=self.base_url,
        )

    async def _get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers with valid access token.

        Returns:
            Dictionary of HTTP headers

        Raises:
            WhoopAPIError: If no valid token available
        """
        access_token = await self.token_manager.get_valid_token(self.user_id)

        if not access_token:
            raise WhoopAPIError("No valid access token available")

        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Whoop API.

        Implements retry logic with exponential backoff for transient failures.

        Args:
            endpoint: API endpoint path (e.g., "/v2/activity/sleep")
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            WhoopAPIError: If request fails after retries
        """
        # Acquire rate limit slot
        await self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"
        headers = await self._get_headers()

        logger.debug(
            "Making API request",
            endpoint=endpoint,
            params=params,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()

                data = response.json()

                logger.debug(
                    "API request successful",
                    endpoint=endpoint,
                    status_code=response.status_code,
                )

                return data

        except httpx.HTTPStatusError as e:
            logger.error(
                "API request failed",
                endpoint=endpoint,
                status_code=e.response.status_code,
                error=e.response.text,
            )
            raise WhoopAPIError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(
                "Network error, will retry",
                endpoint=endpoint,
                error=str(e),
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error during API request",
                endpoint=endpoint,
                error=str(e),
                exc_info=True,
            )
            raise WhoopAPIError(f"Unexpected error: {str(e)}")

    async def _paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        limit: int = 25,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Paginate through API results.

        Whoop API uses cursor-based pagination with next_token.

        Args:
            endpoint: API endpoint path
            params: Initial query parameters
            limit: Records per page (max 25)

        Yields:
            Individual records from paginated response
        """
        params = params or {}
        params["limit"] = min(limit, 25)  # Whoop max is 25
        next_token = None
        page_count = 0

        while True:
            page_count += 1

            # Add pagination token if present
            if next_token:
                params["nextToken"] = next_token

            # Fetch page
            response = await self._make_request(endpoint, params)

            # Extract records
            records = response.get("records", [])
            next_token = response.get("next_token")

            logger.info(
                "Fetched page",
                endpoint=endpoint,
                page=page_count,
                records_count=len(records),
                has_next=bool(next_token),
            )

            # Yield individual records
            for record in records:
                yield record

            # Check if more pages exist
            if not next_token or not records:
                logger.info(
                    "Pagination complete",
                    endpoint=endpoint,
                    total_pages=page_count,
                )
                break

    async def get_sleep_records(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Fetch sleep records for user.

        Args:
            start: Start date for records (inclusive)
            end: End date for records (exclusive)
            limit: Records per page

        Returns:
            List of sleep records
        """
        endpoint = "/developer/v2/activity/sleep"
        params = {}

        if start:
            params["start"] = start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if end:
            params["end"] = end.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        logger.info(
            "Fetching sleep records",
            user_id=self.user_id,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
        )

        records = []
        async for record in self._paginate(endpoint, params, limit):
            records.append(record)

        logger.info(
            "Fetched sleep records",
            user_id=self.user_id,
            count=len(records),
        )

        return records

    async def get_workout_records(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Fetch workout records for user.

        Args:
            start: Start date for records (inclusive)
            end: End date for records (exclusive)
            limit: Records per page

        Returns:
            List of workout records
        """
        endpoint = "/developer/v2/activity/workout"
        params = {}

        if start:
            params["start"] = start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if end:
            params["end"] = end.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        logger.info(
            "Fetching workout records",
            user_id=self.user_id,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
        )

        records = []
        async for record in self._paginate(endpoint, params, limit):
            records.append(record)

        logger.info(
            "Fetched workout records",
            user_id=self.user_id,
            count=len(records),
        )

        return records

    async def get_recovery_records(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Fetch recovery records for user.

        Args:
            start: Start date for records (inclusive)
            end: End date for records (exclusive)
            limit: Records per page

        Returns:
            List of recovery records
        """
        endpoint = "/developer/v2/recovery"
        params = {}

        if start:
            params["start"] = start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if end:
            params["end"] = end.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        logger.info(
            "Fetching recovery records",
            user_id=self.user_id,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
        )

        records = []
        async for record in self._paginate(endpoint, params, limit):
            records.append(record)

        logger.info(
            "Fetched recovery records",
            user_id=self.user_id,
            count=len(records),
        )

        return records

    async def get_cycle_records(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Fetch cycle records for user.

        Args:
            start: Start date for records (inclusive)
            end: End date for records (exclusive)
            limit: Records per page

        Returns:
            List of cycle records
        """
        endpoint = "/developer/v2/cycle"
        params = {}

        if start:
            params["start"] = start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if end:
            params["end"] = end.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        logger.info(
            "Fetching cycle records",
            user_id=self.user_id,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
        )

        records = []
        async for record in self._paginate(endpoint, params, limit):
            records.append(record)

        logger.info(
            "Fetched cycle records",
            user_id=self.user_id,
            count=len(records),
        )

        return records

    async def get_user_profile(self) -> Dict[str, Any]:
        """
        Fetch user profile information.

        Returns:
            User profile data
        """
        endpoint = "/developer/v2/user/profile/basic"

        logger.info("Fetching user profile", user_id=self.user_id)

        response = await self._make_request(endpoint)

        logger.info("Fetched user profile", user_id=self.user_id)

        return response
