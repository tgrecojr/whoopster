"""Tests for token manager."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from src.auth.token_manager import TokenManager
from src.auth.oauth_client import WhoopOAuthClient
from src.auth.encryption import get_token_encryption
from src.models.db_models import OAuthToken


@pytest.mark.unit
class TestTokenManager:
    """Tests for TokenManager class."""

    def test_token_manager_initialization(self):
        """Test token manager initialization."""
        manager = TokenManager()

        assert manager.oauth_client is not None
        assert manager.refresh_threshold == timedelta(minutes=5)

    def test_token_manager_custom_threshold(self):
        """Test token manager with custom refresh threshold."""
        manager = TokenManager(refresh_threshold_minutes=10)

        assert manager.refresh_threshold == timedelta(minutes=10)

    def test_token_manager_custom_oauth_client(self):
        """Test token manager with custom OAuth client."""
        custom_client = WhoopOAuthClient()
        manager = TokenManager(oauth_client=custom_client)

        assert manager.oauth_client is custom_client


@pytest.mark.unit
@pytest.mark.asyncio
class TestTokenManagerAsync:
    """Async tests for TokenManager."""

    async def test_save_token_new(self, db_session, test_user):
        """Test saving a new token."""
        manager = TokenManager()
        encryption = get_token_encryption()

        token = await manager.save_token(
            user_id=test_user.id,
            access_token="test_access",
            refresh_token="test_refresh",
            expires_in=3600,
            token_type="Bearer",
            scopes=["read:sleep"],
            db=db_session,
        )

        assert token.user_id == test_user.id
        # Tokens should be encrypted in database (not plaintext)
        assert token.access_token != "test_access"
        assert token.refresh_token != "test_refresh"
        # Verify tokens can be decrypted correctly
        assert encryption.decrypt(token.access_token) == "test_access"
        assert encryption.decrypt(token.refresh_token) == "test_refresh"
        assert token.token_type == "Bearer"
        assert token.scopes == ["read:sleep"]
        assert token.expires_at > datetime.now(timezone.utc)

    async def test_save_token_update_existing(self, db_session, test_user, test_oauth_token):
        """Test updating an existing token."""
        manager = TokenManager()
        encryption = get_token_encryption()

        original_token_id = test_oauth_token.id

        updated_token = await manager.save_token(
            user_id=test_user.id,
            access_token="new_access",
            refresh_token="new_refresh",
            expires_in=3600,
            db=db_session,
        )

        assert updated_token.id == original_token_id  # Same token, updated
        # Tokens should be encrypted in database
        assert updated_token.access_token != "new_access"
        assert updated_token.refresh_token != "new_refresh"
        # Verify tokens can be decrypted correctly
        assert encryption.decrypt(updated_token.access_token) == "new_access"
        assert encryption.decrypt(updated_token.refresh_token) == "new_refresh"

    async def test_get_valid_token_not_expired(self, db_session, test_user, test_oauth_token):
        """Test getting a valid token that hasn't expired."""
        manager = TokenManager()

        token = await manager.get_valid_token(test_user.id, db=db_session)

        # get_valid_token should return the decrypted token
        assert token == test_oauth_token._plaintext_access_token

    async def test_get_valid_token_no_token(self, db_session, test_user):
        """Test getting token when none exists."""
        manager = TokenManager()

        token = await manager.get_valid_token(test_user.id, db=db_session)

        assert token is None

    async def test_get_valid_token_near_expiry(self, db_session, test_user):
        """Test token refresh when near expiry."""
        manager = TokenManager()
        encryption = get_token_encryption()

        # Create token expiring in 2 minutes (within threshold)
        near_expiry_token = OAuthToken(
            user_id=test_user.id,
            access_token=encryption.encrypt("old_access"),
            refresh_token=encryption.encrypt("old_refresh"),
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            scopes=["read:sleep"],
        )
        db_session.add(near_expiry_token)
        db_session.commit()

        # Mock refresh token response
        mock_response = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(
            manager.oauth_client,
            "refresh_access_token",
            new=AsyncMock(return_value=mock_response),
        ):
            token = await manager.get_valid_token(test_user.id, db=db_session)

            # Should have refreshed the token
            assert token == "new_access"

            # Check database was updated with encrypted token
            db_session.refresh(near_expiry_token)
            assert encryption.decrypt(near_expiry_token.access_token) == "new_access"

    async def test_is_token_valid_true(self, db_session, test_user, test_oauth_token):
        """Test checking if token is valid."""
        manager = TokenManager()

        is_valid = await manager.is_token_valid(test_user.id, db=db_session)

        assert is_valid is True

    async def test_is_token_valid_false_no_token(self, db_session, test_user):
        """Test checking validity when no token exists."""
        manager = TokenManager()

        is_valid = await manager.is_token_valid(test_user.id, db=db_session)

        assert is_valid is False

    async def test_is_token_valid_false_expired(self, db_session, test_user, expired_oauth_token):
        """Test checking validity with expired token."""
        manager = TokenManager()

        is_valid = await manager.is_token_valid(test_user.id, db=db_session)

        assert is_valid is False

    async def test_delete_token(self, db_session, test_user, test_oauth_token):
        """Test deleting a token."""
        manager = TokenManager()

        result = await manager.delete_token(test_user.id, db=db_session)

        assert result is True

        # Verify token was deleted
        deleted = db_session.query(OAuthToken).filter_by(id=test_oauth_token.id).first()
        assert deleted is None

    async def test_delete_token_not_exists(self, db_session, test_user):
        """Test deleting token when none exists."""
        manager = TokenManager()

        result = await manager.delete_token(test_user.id, db=db_session)

        assert result is False

    async def test_get_token_info(self, db_session, test_user, test_oauth_token):
        """Test getting token information."""
        manager = TokenManager()

        info = await manager.get_token_info(test_user.id, db=db_session)

        assert info is not None
        assert info["user_id"] == test_user.id
        assert info["token_type"] == "Bearer"
        assert info["scopes"] == test_oauth_token.scopes
        assert "expires_at" in info
        assert "seconds_until_expiry" in info
        assert info["is_expired"] is False

    async def test_get_token_info_expired(self, db_session, test_user, expired_oauth_token):
        """Test getting info for expired token."""
        manager = TokenManager()

        info = await manager.get_token_info(test_user.id, db=db_session)

        assert info is not None
        assert info["is_expired"] is True
        assert info["seconds_until_expiry"] < 0

    async def test_get_token_info_needs_refresh(self, db_session, test_user):
        """Test token info shows needs refresh."""
        manager = TokenManager()
        encryption = get_token_encryption()

        # Create token expiring in 2 minutes (within threshold)
        near_expiry_token = OAuthToken(
            user_id=test_user.id,
            access_token=encryption.encrypt("access"),
            refresh_token=encryption.encrypt("refresh"),
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            scopes=["read:sleep"],
        )
        db_session.add(near_expiry_token)
        db_session.commit()

        info = await manager.get_token_info(test_user.id, db=db_session)

        assert info is not None
        assert info["needs_refresh"] is True
        assert info["is_expired"] is False

    async def test_get_token_info_no_token(self, db_session, test_user):
        """Test getting info when no token exists."""
        manager = TokenManager()

        info = await manager.get_token_info(test_user.id, db=db_session)

        assert info is None
