"""Tests for OAuth client."""

import pytest
import respx
import httpx
from urllib.parse import urlparse, parse_qs

from src.auth.oauth_client import WhoopOAuthClient


@pytest.mark.unit
class TestWhoopOAuthClient:
    """Tests for WhoopOAuthClient class."""

    def test_oauth_client_initialization(self):
        """Test OAuth client initialization."""
        client = WhoopOAuthClient()

        assert client.client_id is not None
        assert client.client_secret is not None
        assert client.redirect_uri is not None
        assert client.auth_url is not None
        assert client.token_url is not None
        assert "read:sleep" in client.scopes
        assert "read:workout" in client.scopes
        assert "read:recovery" in client.scopes
        assert "read:cycles" in client.scopes
        assert "offline" in client.scopes

    def test_generate_pkce_pair(self):
        """Test PKCE pair generation."""
        client = WhoopOAuthClient()

        code_verifier, code_challenge = client.generate_pkce_pair()

        assert len(code_verifier) >= 43
        assert len(code_challenge) > 0
        assert code_verifier != code_challenge

    def test_generate_pkce_pair_unique(self):
        """Test that PKCE pairs are unique."""
        client = WhoopOAuthClient()

        verifier1, challenge1 = client.generate_pkce_pair()
        verifier2, challenge2 = client.generate_pkce_pair()

        assert verifier1 != verifier2
        assert challenge1 != challenge2

    def test_get_authorization_url(self):
        """Test authorization URL generation."""
        client = WhoopOAuthClient()

        auth_url, state, code_verifier = client.get_authorization_url()

        # Parse URL
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)

        assert client.auth_url in auth_url
        assert params["client_id"][0] == client.client_id
        assert params["redirect_uri"][0] == client.redirect_uri
        assert params["response_type"][0] == "code"
        assert params["state"][0] == state
        assert "code_challenge" in params
        assert params["code_challenge_method"][0] == "S256"
        assert len(state) > 0
        assert len(code_verifier) > 0

    def test_get_authorization_url_with_custom_state(self):
        """Test authorization URL with custom state."""
        client = WhoopOAuthClient()
        custom_state = "my_custom_state"

        auth_url, state, code_verifier = client.get_authorization_url(state=custom_state)

        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)

        assert params["state"][0] == custom_state
        assert state == custom_state

    def test_authorization_url_includes_scopes(self):
        """Test that authorization URL includes all scopes."""
        client = WhoopOAuthClient()

        auth_url, state, code_verifier = client.get_authorization_url()

        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)
        scopes = params["scope"][0].split(" ")

        assert "read:sleep" in scopes
        assert "read:workout" in scopes
        assert "read:recovery" in scopes
        assert "read:cycles" in scopes
        assert "offline" in scopes


@pytest.mark.unit
@pytest.mark.asyncio
class TestWhoopOAuthClientAsync:
    """Async tests for WhoopOAuthClient."""

    @respx.mock
    async def test_exchange_code_for_token_success(self):
        """Test successful token exchange."""
        client = WhoopOAuthClient()

        # Mock token endpoint
        mock_response = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read:sleep read:workout",
        }

        respx.post(client.token_url).mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        # Exchange code
        token_data = await client.exchange_code_for_token(
            code="test_code",
            code_verifier="test_verifier",
        )

        assert token_data["access_token"] == "test_access_token"
        assert token_data["refresh_token"] == "test_refresh_token"
        assert token_data["token_type"] == "Bearer"
        assert token_data["expires_in"] == 3600

    @respx.mock
    async def test_exchange_code_for_token_failure(self):
        """Test failed token exchange."""
        client = WhoopOAuthClient()

        # Mock failed response
        respx.post(client.token_url).mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )

        # Should raise HTTPStatusError
        with pytest.raises(httpx.HTTPStatusError):
            await client.exchange_code_for_token(
                code="invalid_code",
                code_verifier="test_verifier",
            )

    @respx.mock
    async def test_refresh_access_token_success(self):
        """Test successful token refresh."""
        client = WhoopOAuthClient()

        # Mock token endpoint
        mock_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        respx.post(client.token_url).mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        # Refresh token
        token_data = await client.refresh_access_token(
            refresh_token="old_refresh_token"
        )

        assert token_data["access_token"] == "new_access_token"
        assert token_data["refresh_token"] == "new_refresh_token"
        assert token_data["expires_in"] == 3600

    @respx.mock
    async def test_refresh_access_token_failure(self):
        """Test failed token refresh."""
        client = WhoopOAuthClient()

        # Mock failed response
        respx.post(client.token_url).mock(
            return_value=httpx.Response(400, json={"error": "invalid_token"})
        )

        # Should raise HTTPStatusError
        with pytest.raises(httpx.HTTPStatusError):
            await client.refresh_access_token(
                refresh_token="invalid_refresh_token"
            )

    @respx.mock
    async def test_exchange_code_network_error(self):
        """Test token exchange with network error."""
        client = WhoopOAuthClient()

        # Mock network error
        respx.post(client.token_url).mock(side_effect=httpx.NetworkError)

        # Should raise NetworkError
        with pytest.raises(httpx.NetworkError):
            await client.exchange_code_for_token(
                code="test_code",
                code_verifier="test_verifier",
            )

    async def test_revoke_token_not_implemented(self):
        """Test that token revocation returns False (not implemented)."""
        client = WhoopOAuthClient()

        result = await client.revoke_token("test_token")

        assert result is False
