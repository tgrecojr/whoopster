"""Token management for Whoop API OAuth tokens.

This module handles storage, retrieval, and automatic refresh of OAuth tokens
in the PostgreSQL database with encryption at rest.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.db_models import User, OAuthToken
from src.auth.oauth_client import WhoopOAuthClient
from src.auth.encryption import get_token_encryption
from src.database.session import get_db_context
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class TokenManager:
    """
    Manages OAuth token lifecycle for Whoop API.

    Handles token storage in database, automatic refresh when near expiration,
    and retrieval of valid tokens for API requests.

    Attributes:
        oauth_client: OAuth client for token refresh operations
        refresh_threshold: Time before expiry to trigger refresh (minutes)
    """

    def __init__(
        self,
        oauth_client: Optional[WhoopOAuthClient] = None,
        refresh_threshold_minutes: int = 5,
    ) -> None:
        """
        Initialize token manager.

        Args:
            oauth_client: OAuth client instance (creates new if None)
            refresh_threshold_minutes: Minutes before expiry to refresh token
        """
        self.oauth_client = oauth_client or WhoopOAuthClient()
        self.refresh_threshold = timedelta(minutes=refresh_threshold_minutes)

        logger.info(
            "Token manager initialized",
            refresh_threshold_minutes=refresh_threshold_minutes,
        )

    async def save_token(
        self,
        user_id: int,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        token_type: str = "Bearer",
        scopes: Optional[list[str]] = None,
        db: Optional[Session] = None,
    ) -> OAuthToken:
        """
        Save OAuth tokens to database.

        Creates or updates token record for the specified user.

        Args:
            user_id: User database ID
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            expires_in: Token lifetime in seconds
            token_type: Token type (usually "Bearer")
            scopes: List of granted OAuth scopes
            db: Database session (creates new if None)

        Returns:
            Saved OAuthToken instance
        """
        # Calculate expiration timestamp
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        def _save_token_sync(session: Session) -> OAuthToken:
            # Get encryption instance
            encryption = get_token_encryption()

            # Encrypt tokens before storage
            encrypted_access_token = encryption.encrypt(access_token)
            encrypted_refresh_token = encryption.encrypt(refresh_token)

            # Check if token already exists for user
            stmt = select(OAuthToken).where(OAuthToken.user_id == user_id)
            existing_token = session.execute(stmt).scalar_one_or_none()

            if existing_token:
                # Update existing token with encrypted values
                existing_token.access_token = encrypted_access_token
                existing_token.refresh_token = encrypted_refresh_token
                existing_token.token_type = token_type
                existing_token.expires_at = expires_at
                existing_token.scopes = scopes
                existing_token.updated_at = datetime.now(timezone.utc)

                logger.info(
                    "Updated existing token (encrypted)",
                    user_id=user_id,
                    expires_at=expires_at.isoformat(),
                )

                return existing_token
            else:
                # Create new token with encrypted values
                new_token = OAuthToken(
                    user_id=user_id,
                    access_token=encrypted_access_token,
                    refresh_token=encrypted_refresh_token,
                    token_type=token_type,
                    expires_at=expires_at,
                    scopes=scopes,
                )

                session.add(new_token)

                logger.info(
                    "Created new token (encrypted)",
                    user_id=user_id,
                    expires_at=expires_at.isoformat(),
                )

                return new_token

        # Use provided session or create new one
        if db:
            return _save_token_sync(db)
        else:
            with get_db_context() as session:
                return _save_token_sync(session)

    async def get_valid_token(
        self,
        user_id: int,
        db: Optional[Session] = None,
    ) -> Optional[str]:
        """
        Get a valid access token for the user.

        Automatically refreshes token if it's near expiration.

        Args:
            user_id: User database ID
            db: Database session (creates new if None)

        Returns:
            Valid access token or None if no token exists

        Raises:
            Exception: If token refresh fails
        """

        def _get_token_sync(session: Session) -> Optional[str]:
            # Get encryption instance
            encryption = get_token_encryption()

            # Retrieve user's token from database
            stmt = select(OAuthToken).where(OAuthToken.user_id == user_id)
            token = session.execute(stmt).scalar_one_or_none()

            if not token:
                logger.warning("No token found for user", user_id=user_id)
                return None

            # Decrypt tokens
            try:
                decrypted_access_token = encryption.decrypt(token.access_token)
                decrypted_refresh_token = encryption.decrypt(token.refresh_token)
            except Exception as e:
                logger.error(
                    "Failed to decrypt token",
                    user_id=user_id,
                    error=str(e),
                )
                raise

            # Check if token needs refresh
            now = datetime.now(timezone.utc)
            # Handle both timezone-aware and naive datetimes (SQLite may strip timezone)
            token_expiry = token.expires_at
            if token_expiry.tzinfo is None:
                # If token is naive, make it UTC-aware
                token_expiry = token_expiry.replace(tzinfo=timezone.utc)
            time_until_expiry = token_expiry - now

            if time_until_expiry <= self.refresh_threshold:
                logger.info(
                    "Token near expiration, refreshing",
                    user_id=user_id,
                    time_until_expiry_seconds=time_until_expiry.total_seconds(),
                )

                # Refresh token asynchronously
                import asyncio
                import concurrent.futures

                try:
                    # Check if there's a running event loop (e.g., in async tests)
                    try:
                        loop = asyncio.get_running_loop()
                        # If loop is running, we need to run the async code in a thread pool
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(
                                asyncio.run,
                                self.oauth_client.refresh_access_token(decrypted_refresh_token)
                            )
                            token_data = future.result()
                    except RuntimeError:
                        # No running loop, we can use run_until_complete
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        token_data = loop.run_until_complete(
                            self.oauth_client.refresh_access_token(decrypted_refresh_token)
                        )

                    # Encrypt new tokens before updating database
                    encrypted_access_token = encryption.encrypt(token_data["access_token"])
                    encrypted_refresh_token = encryption.encrypt(
                        token_data.get("refresh_token", decrypted_refresh_token)
                    )

                    # Update token in database with encrypted values
                    token.access_token = encrypted_access_token
                    token.refresh_token = encrypted_refresh_token
                    token.token_type = token_data.get("token_type", token.token_type)
                    token.expires_at = datetime.now(timezone.utc) + timedelta(
                        seconds=token_data["expires_in"]
                    )
                    token.updated_at = datetime.now(timezone.utc)

                    session.commit()

                    logger.info(
                        "Token refreshed successfully (encrypted)",
                        user_id=user_id,
                        new_expires_at=token.expires_at.isoformat(),
                    )

                    # Return the new decrypted access token
                    return token_data["access_token"]

                except Exception as e:
                    logger.error(
                        "Failed to refresh token",
                        user_id=user_id,
                        error=str(e),
                        exc_info=True,
                    )
                    raise

            # Return decrypted access token
            return decrypted_access_token

        # Use provided session or create new one
        if db:
            return _get_token_sync(db)
        else:
            with get_db_context() as session:
                return _get_token_sync(session)

    async def is_token_valid(
        self,
        user_id: int,
        db: Optional[Session] = None,
    ) -> bool:
        """
        Check if user has a valid token.

        Args:
            user_id: User database ID
            db: Database session (creates new if None)

        Returns:
            True if valid token exists, False otherwise
        """

        def _check_token_sync(session: Session) -> bool:
            stmt = select(OAuthToken).where(OAuthToken.user_id == user_id)
            token = session.execute(stmt).scalar_one_or_none()

            if not token:
                return False

            # Check expiration
            now = datetime.now(timezone.utc)
            # Handle both timezone-aware and naive datetimes (SQLite may strip timezone)
            token_expiry = token.expires_at
            if token_expiry.tzinfo is None:
                token_expiry = token_expiry.replace(tzinfo=timezone.utc)
            return token_expiry > now

        if db:
            return _check_token_sync(db)
        else:
            with get_db_context() as session:
                return _check_token_sync(session)

    async def delete_token(
        self,
        user_id: int,
        db: Optional[Session] = None,
    ) -> bool:
        """
        Delete user's OAuth token.

        Args:
            user_id: User database ID
            db: Database session (creates new if None)

        Returns:
            True if token deleted, False if no token existed
        """

        def _delete_token_sync(session: Session) -> bool:
            stmt = select(OAuthToken).where(OAuthToken.user_id == user_id)
            token = session.execute(stmt).scalar_one_or_none()

            if token:
                session.delete(token)
                session.flush()  # Flush to make deletion visible
                logger.info("Deleted token", user_id=user_id)
                return True
            else:
                logger.warning("No token to delete", user_id=user_id)
                return False

        if db:
            return _delete_token_sync(db)
        else:
            with get_db_context() as session:
                return _delete_token_sync(session)

    async def get_token_info(
        self,
        user_id: int,
        db: Optional[Session] = None,
    ) -> Optional[dict]:
        """
        Get token information for monitoring/debugging.

        Args:
            user_id: User database ID
            db: Database session (creates new if None)

        Returns:
            Dictionary with token info or None if no token
        """

        def _get_info_sync(session: Session) -> Optional[dict]:
            stmt = select(OAuthToken).where(OAuthToken.user_id == user_id)
            token = session.execute(stmt).scalar_one_or_none()

            if not token:
                return None

            now = datetime.now(timezone.utc)
            # Handle both timezone-aware and naive datetimes (SQLite may strip timezone)
            token_expiry = token.expires_at
            if token_expiry.tzinfo is None:
                token_expiry = token_expiry.replace(tzinfo=timezone.utc)
            time_until_expiry = token_expiry - now

            return {
                "user_id": token.user_id,
                "token_type": token.token_type,
                "scopes": token.scopes,
                "expires_at": token_expiry.isoformat(),
                "seconds_until_expiry": time_until_expiry.total_seconds(),
                "is_expired": time_until_expiry.total_seconds() <= 0,
                "needs_refresh": time_until_expiry <= self.refresh_threshold,
                "created_at": token.created_at.isoformat() if token.created_at else None,
                "updated_at": token.updated_at.isoformat() if token.updated_at else None,
            }

        if db:
            return _get_info_sync(db)
        else:
            with get_db_context() as session:
                return _get_info_sync(session)
