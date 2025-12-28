"""Tests for Whoop API client."""

import pytest
import respx
import httpx
from unittest.mock import AsyncMock, patch

from src.api.whoop_client import WhoopClient, WhoopAPIError
from src.auth.token_manager import TokenManager
from src.api.rate_limiter import RateLimiter


@pytest.mark.unit
class TestWhoopClient:
    """Tests for WhoopClient class."""

    def test_whoop_client_initialization(self, test_user):
        """Test Whoop client initialization."""
        client = WhoopClient(user_id=test_user.id)

        assert client.user_id == test_user.id
        assert client.token_manager is not None
        assert client.rate_limiter is not None
        assert client.timeout == 30.0

    def test_whoop_client_custom_components(self, test_user):
        """Test Whoop client with custom components."""
        token_manager = TokenManager()
        rate_limiter = RateLimiter()

        client = WhoopClient(
            user_id=test_user.id,
            token_manager=token_manager,
            rate_limiter=rate_limiter,
            timeout=60.0,
        )

        assert client.token_manager is token_manager
        assert client.rate_limiter is rate_limiter
        assert client.timeout == 60.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestWhoopClientAsync:
    """Async tests for WhoopClient."""

    async def test_get_headers_success(self, test_user, test_oauth_token, db_session):
        """Test getting headers with valid token."""
        client = WhoopClient(user_id=test_user.id)

        # Mock token manager
        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=test_oauth_token.access_token),
        ):
            headers = await client._get_headers()

            assert "Authorization" in headers
            assert headers["Authorization"] == f"Bearer {test_oauth_token.access_token}"
            assert headers["Accept"] == "application/json"

    async def test_get_headers_no_token(self, test_user):
        """Test getting headers when no token available."""
        client = WhoopClient(user_id=test_user.id)

        # Mock token manager to return None
        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(WhoopAPIError, match="No valid access token"):
                await client._get_headers()

    @respx.mock
    async def test_make_request_success(self, test_user, test_oauth_token):
        """Test successful API request."""
        client = WhoopClient(user_id=test_user.id)

        # Mock token
        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            # Mock rate limiter
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                # Mock API response
                mock_response = {"data": "test"}
                respx.get(f"{client.base_url}/test").mock(
                    return_value=httpx.Response(200, json=mock_response)
                )

                response = await client._make_request("/test")

                assert response == mock_response

    @respx.mock
    async def test_make_request_http_error(self, test_user):
        """Test API request with HTTP error."""
        client = WhoopClient(user_id=test_user.id)

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                # Mock 404 response
                respx.get(f"{client.base_url}/test").mock(
                    return_value=httpx.Response(404, json={"error": "Not found"})
                )

                with pytest.raises(WhoopAPIError):
                    await client._make_request("/test")

    @respx.mock
    async def test_get_sleep_records(self, test_user, mock_whoop_sleep_response):
        """Test fetching sleep records."""
        client = WhoopClient(user_id=test_user.id)

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                respx.get(f"{client.base_url}/developer/v1/activity/sleep").mock(
                    return_value=httpx.Response(200, json=mock_whoop_sleep_response)
                )

                records = await client.get_sleep_records()

                assert len(records) == 1
                assert "id" in records[0]

    @respx.mock
    async def test_get_workout_records(self, test_user, mock_whoop_workout_response):
        """Test fetching workout records."""
        client = WhoopClient(user_id=test_user.id)

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                respx.get(f"{client.base_url}/developer/v1/activity/workout").mock(
                    return_value=httpx.Response(200, json=mock_whoop_workout_response)
                )

                records = await client.get_workout_records()

                assert len(records) == 1
                assert records[0]["sport_name"] == "Running"

    @respx.mock
    async def test_get_recovery_records(self, test_user, mock_whoop_recovery_response):
        """Test fetching recovery records."""
        client = WhoopClient(user_id=test_user.id)

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                respx.get(f"{client.base_url}/developer/v1/recovery").mock(
                    return_value=httpx.Response(200, json=mock_whoop_recovery_response)
                )

                records = await client.get_recovery_records()

                assert len(records) == 1
                assert "recovery_score" in records[0]["score"]

    @respx.mock
    async def test_get_cycle_records(self, test_user, mock_whoop_cycle_response):
        """Test fetching cycle records."""
        client = WhoopClient(user_id=test_user.id)

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                respx.get(f"{client.base_url}/developer/v1/cycle").mock(
                    return_value=httpx.Response(200, json=mock_whoop_cycle_response)
                )

                records = await client.get_cycle_records()

                assert len(records) == 1

    @respx.mock
    async def test_get_user_profile(self, test_user, mock_whoop_user_profile):
        """Test fetching user profile."""
        client = WhoopClient(user_id=test_user.id)

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                respx.get(f"{client.base_url}/developer/v1/user/profile/basic").mock(
                    return_value=httpx.Response(200, json=mock_whoop_user_profile)
                )

                profile = await client.get_user_profile()

                assert profile["first_name"] == "Test"
                assert profile["last_name"] == "User"

    @respx.mock
    async def test_pagination(self, test_user):
        """Test pagination handling."""
        client = WhoopClient(user_id=test_user.id)

        # First page
        page1 = {
            "records": [{"id": "1"}],
            "next_token": "token_page2",
        }

        # Second page
        page2 = {
            "records": [{"id": "2"}],
            "next_token": None,
        }

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                # Mock paginated responses
                route = respx.get(f"{client.base_url}/developer/v1/activity/sleep")
                route.side_effect = [
                    httpx.Response(200, json=page1),
                    httpx.Response(200, json=page2),
                ]

                records = await client.get_sleep_records()

                # Should have records from both pages
                assert len(records) == 2
                assert records[0]["id"] == "1"
                assert records[1]["id"] == "2"

    @respx.mock
    async def test_request_with_date_range(self, test_user, date_range):
        """Test request with date range parameters."""
        client = WhoopClient(user_id=test_user.id)
        start, end = date_range

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value="test_token"),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                mock_response = {"records": [], "next_token": None}
                route = respx.get(f"{client.base_url}/developer/v1/activity/sleep")
                route.mock(return_value=httpx.Response(200, json=mock_response))

                await client.get_sleep_records(start=start, end=end)

                # Verify date parameters were sent
                request = route.calls.last.request
                assert "start" in str(request.url)
                assert "end" in str(request.url)
