"""OAuth 2.0 client for Whoop API authentication.

This module implements the OAuth 2.0 authorization code flow with PKCE
for secure authentication with the Whoop API.
"""

import secrets
import hashlib
import base64
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import httpx
from authlib.oauth2.rfc7636 import create_s256_code_challenge

from src.config import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class WhoopOAuthClient:
    """
    OAuth 2.0 client for Whoop API authentication.

    Implements authorization code flow with PKCE (Proof Key for Code Exchange)
    for enhanced security. Handles authorization URL generation and token exchange.

    Attributes:
        client_id: Whoop application client ID
        client_secret: Whoop application client secret
        redirect_uri: OAuth callback URL
        auth_url: Whoop authorization endpoint
        token_url: Whoop token endpoint
        scopes: List of requested OAuth scopes
    """

    def __init__(self) -> None:
        """Initialize OAuth client with settings from environment."""
        self.client_id = settings.whoop_client_id
        self.client_secret = settings.whoop_client_secret
        self.redirect_uri = settings.whoop_redirect_uri
        self.auth_url = settings.whoop_auth_url
        self.token_url = settings.whoop_token_url

        # Required scopes for data access
        self.scopes = [
            "read:sleep",
            "read:workout",
            "read:recovery",
            "read:cycles",
            "offline",  # For refresh tokens
        ]

        logger.info(
            "OAuth client initialized",
            client_id=self.client_id[:8] + "...",  # Log partial ID for privacy
            redirect_uri=self.redirect_uri,
            scopes=self.scopes,
        )

    def generate_pkce_pair(self) -> tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.

        PKCE (RFC 7636) adds security to OAuth flow by requiring the client
        to prove it initiated the authorization request.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate cryptographically secure random verifier (43-128 chars)
        code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode('utf-8').rstrip('=')

        # Create SHA256 challenge from verifier
        code_challenge = create_s256_code_challenge(code_verifier)

        logger.debug(
            "Generated PKCE pair",
            verifier_length=len(code_verifier),
            challenge=code_challenge[:10] + "...",
        )

        return code_verifier, code_challenge

    def get_authorization_url(
        self,
        state: Optional[str] = None,
    ) -> tuple[str, str, str]:
        """
        Generate authorization URL for user consent.

        Creates the URL users visit to grant access to their Whoop data.
        Implements PKCE for enhanced security.

        Args:
            state: Optional CSRF token for request validation

        Returns:
            Tuple of (authorization_url, state, code_verifier)
        """
        # Generate PKCE parameters
        code_verifier, code_challenge = self.generate_pkce_pair()

        # Generate state token if not provided (CSRF protection)
        if state is None:
            state = secrets.token_urlsafe(32)

        # Build authorization parameters
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        # Construct full URL
        auth_url = f"{self.auth_url}?{urlencode(params)}"

        logger.info(
            "Generated authorization URL",
            state=state[:10] + "...",
            scopes=self.scopes,
        )

        return auth_url, state, code_verifier

    async def exchange_code_for_token(
        self,
        code: str,
        code_verifier: str,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.

        After user grants consent, exchange the authorization code for
        access and refresh tokens.

        Args:
            code: Authorization code from callback
            code_verifier: PKCE verifier used in authorization request

        Returns:
            Token response containing access_token, refresh_token, expires_in, etc.

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        # Build token request payload
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code_verifier": code_verifier,
        }

        logger.info(
            "Exchanging authorization code for token",
            code=code[:10] + "...",
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()

                token_data = response.json()

                logger.info(
                    "Successfully exchanged code for token",
                    token_type=token_data.get("token_type"),
                    expires_in=token_data.get("expires_in"),
                    scopes=token_data.get("scope"),
                )

                return token_data

        except httpx.HTTPStatusError as e:
            logger.error(
                "Token exchange failed",
                status_code=e.response.status_code,
                error=e.response.text,
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error during token exchange",
                error=str(e),
                exc_info=True,
            )
            raise

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> Dict[str, Any]:
        """
        Refresh an expired access token.

        Uses the refresh token to obtain a new access token without
        requiring user interaction.

        Args:
            refresh_token: Valid refresh token from previous authorization

        Returns:
            Token response with new access_token and possibly new refresh_token

        Raises:
            httpx.HTTPStatusError: If refresh fails (token expired/revoked)
        """
        # Build refresh request payload
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        logger.info("Refreshing access token")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()

                token_data = response.json()

                logger.info(
                    "Successfully refreshed access token",
                    token_type=token_data.get("token_type"),
                    expires_in=token_data.get("expires_in"),
                )

                return token_data

        except httpx.HTTPStatusError as e:
            logger.error(
                "Token refresh failed",
                status_code=e.response.status_code,
                error=e.response.text,
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error during token refresh",
                error=str(e),
                exc_info=True,
            )
            raise

    async def revoke_token(
        self,
        token: str,
        token_type_hint: str = "access_token",
    ) -> bool:
        """
        Revoke an access or refresh token.

        Args:
            token: Token to revoke
            token_type_hint: Type of token ("access_token" or "refresh_token")

        Returns:
            True if revocation successful, False otherwise
        """
        # Note: Whoop API may not support token revocation endpoint
        # This is a placeholder for future implementation
        logger.warning(
            "Token revocation not yet implemented",
            token_type_hint=token_type_hint,
        )
        return False
