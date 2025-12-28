#!/usr/bin/env python3
"""Interactive OAuth setup script for Whoopster.

This script guides users through the OAuth 2.0 authorization flow
to grant access to their Whoop data.

Usage:
    # Normal mode (with browser)
    python scripts/init_oauth.py

    # Headless mode (for servers without browser)
    python scripts/init_oauth.py --headless
"""

import asyncio
import sys
import argparse
import webbrowser
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple

from sqlalchemy import select

sys.path.insert(0, ".")

from src.auth.oauth_client import WhoopOAuthClient
from src.auth.token_manager import TokenManager
from src.models.db_models import User
from src.database.session import get_db_context
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    auth_code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        """Handle GET request to callback URL."""
        # Parse query parameters
        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)

        # Extract authorization code and state
        OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
        OAuthCallbackHandler.state = params.get("state", [None])[0]
        OAuthCallbackHandler.error = params.get("error", [None])[0]

        # Send response to browser
        if OAuthCallbackHandler.error:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<h1>Authorization Failed</h1>"
                b"<p>Error: " + OAuthCallbackHandler.error.encode() + b"</p>"
                b"<p>You can close this window.</p>"
                b"</body></html>"
            )
        elif OAuthCallbackHandler.auth_code:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<h1>Authorization Successful!</h1>"
                b"<p>You have successfully authorized Whoopster.</p>"
                b"<p>You can close this window and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<h1>Invalid Request</h1>"
                b"<p>No authorization code received.</p>"
                b"</body></html>"
            )

    def log_message(self, format, *args):
        """Suppress access log messages."""
        pass


async def wait_for_callback(
    server: HTTPServer,
    timeout: int = 300,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Wait for OAuth callback.

    Args:
        server: HTTP server instance
        timeout: Timeout in seconds

    Returns:
        Tuple of (auth_code, state, error)
    """
    # Run server in event loop with timeout
    loop = asyncio.get_event_loop()

    def serve():
        server.handle_request()

    # Wait for callback with timeout
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, serve),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for OAuth callback")
        return None, None, "timeout"

    return (
        OAuthCallbackHandler.auth_code,
        OAuthCallbackHandler.state,
        OAuthCallbackHandler.error,
    )


async def setup_oauth_headless(
    whoop_user_id: Optional[str] = None,
    email: Optional[str] = None,
) -> bool:
    """
    Run OAuth setup in headless mode (for servers without browser).

    Args:
        whoop_user_id: Whoop user ID (optional, for reference)
        email: User email (optional)

    Returns:
        True if setup successful, False otherwise
    """
    print("\n" + "=" * 70)
    print("Whoopster OAuth Setup (Headless Mode)")
    print("=" * 70 + "\n")

    print("This mode is for headless servers without a browser.")
    print("You'll authorize on another device and paste the callback URL here.\n")

    # Initialize OAuth client
    oauth_client = WhoopOAuthClient()
    token_manager = TokenManager(oauth_client)

    # Generate authorization URL
    print("Step 1: Generating authorization URL...\n")
    auth_url, state, code_verifier = oauth_client.get_authorization_url()

    print("=" * 70)
    print("AUTHORIZATION URL")
    print("=" * 70)
    print("\nCopy this URL and open it in a browser on ANY device:")
    print(f"\n{auth_url}\n")
    print("=" * 70 + "\n")

    print("Step 2: After authorizing, you'll be redirected to a callback URL.")
    print("         The URL will look like:")
    print(f"         {oauth_client.redirect_uri}?code=XXXXX&state=XXXXX\n")
    print("         Copy the ENTIRE callback URL and paste it below.\n")

    # Get callback URL from user
    while True:
        callback_url = input("Paste the full callback URL here: ").strip()

        if not callback_url:
            print("Error: No URL provided. Please try again.")
            continue

        # Parse callback URL
        try:
            parsed_url = urlparse(callback_url)
            params = parse_qs(parsed_url.query)

            auth_code = params.get("code", [None])[0]
            received_state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]

            if error:
                print(f"\nError: Authorization failed - {error}")
                return False

            if not auth_code:
                print("\nError: No authorization code found in URL.")
                print("Make sure you copied the complete callback URL.\n")
                retry = input("Try again? (yes/no): ").strip().lower()
                if retry not in ["yes", "y"]:
                    return False
                continue

            if received_state != state:
                print("\nError: State mismatch (possible security issue)")
                print("Please start the OAuth process again.")
                return False

            print("\n✓ Authorization code extracted successfully\n")
            break

        except Exception as e:
            print(f"\nError parsing URL: {e}")
            print("Make sure you copied the complete callback URL.\n")
            retry = input("Try again? (yes/no): ").strip().lower()
            if retry not in ["yes", "y"]:
                return False
            continue

    # Exchange code for tokens (continue with same flow as normal mode)
    print("Step 3: Exchanging authorization code for access token...\n")

    try:
        token_data = await oauth_client.exchange_code_for_token(
            code=auth_code,
            code_verifier=code_verifier,
        )

        print("✓ Access token obtained\n")

    except Exception as e:
        print(f"\nError: Failed to exchange code for token")
        print(f"Details: {e}")
        return False

    # Save tokens (same as normal mode)
    return await save_user_and_tokens(
        token_manager=token_manager,
        token_data=token_data,
        whoop_user_id=whoop_user_id,
        email=email,
    )


async def setup_oauth(
    whoop_user_id: Optional[str] = None,
    email: Optional[str] = None,
) -> bool:
    """
    Run interactive OAuth setup (normal mode with browser).

    Args:
        whoop_user_id: Whoop user ID (optional, for reference)
        email: User email (optional)

    Returns:
        True if setup successful, False otherwise
    """
    print("\n" + "=" * 60)
    print("Whoopster OAuth Setup")
    print("=" * 60 + "\n")

    print("This script will guide you through authorizing Whoopster")
    print("to access your Whoop data.\n")

    # Initialize OAuth client
    oauth_client = WhoopOAuthClient()
    token_manager = TokenManager(oauth_client)

    # Generate authorization URL
    print("Step 1: Generating authorization URL...\n")
    auth_url, state, code_verifier = oauth_client.get_authorization_url()

    print(f"Authorization URL generated.\n")

    # Start local server for callback
    print("Step 2: Starting local callback server...\n")

    # Parse redirect URI to get port
    from urllib.parse import urlparse
    parsed_uri = urlparse(oauth_client.redirect_uri)
    port = parsed_uri.port or 8000

    try:
        server = HTTPServer(("localhost", port), OAuthCallbackHandler)
        print(f"Callback server running on port {port}\n")
    except OSError as e:
        print(f"Error: Could not start server on port {port}")
        print(f"Make sure port {port} is not in use.\n")
        print(f"Error details: {e}")
        return False

    # Open browser
    print("Step 3: Opening browser for authorization...\n")
    print("If the browser doesn't open automatically, copy this URL:")
    print(f"\n{auth_url}\n")

    webbrowser.open(auth_url)

    print("Waiting for authorization (this will timeout in 5 minutes)...\n")

    # Wait for callback
    auth_code, received_state, error = await wait_for_callback(server, timeout=300)

    server.server_close()

    if error:
        print(f"\nError: Authorization failed - {error}")
        return False

    if not auth_code:
        print("\nError: No authorization code received")
        return False

    if received_state != state:
        print("\nError: State mismatch (possible CSRF attack)")
        return False

    print("✓ Authorization code received\n")

    # Exchange code for tokens
    print("Step 4: Exchanging authorization code for access token...\n")

    try:
        token_data = await oauth_client.exchange_code_for_token(
            code=auth_code,
            code_verifier=code_verifier,
        )

        print("✓ Access token obtained\n")

    except Exception as e:
        print(f"\nError: Failed to exchange code for token")
        print(f"Details: {e}")
        return False

    # Save tokens
    return await save_user_and_tokens(
        token_manager=token_manager,
        token_data=token_data,
        whoop_user_id=whoop_user_id,
        email=email,
    )


async def save_user_and_tokens(
    token_manager: TokenManager,
    token_data: dict,
    whoop_user_id: Optional[str] = None,
    email: Optional[str] = None,
) -> bool:
    """
    Save user and OAuth tokens to database.

    Args:
        token_manager: Token manager instance
        token_data: OAuth token data
        whoop_user_id: Whoop user ID (optional)
        email: User email (optional)

    Returns:
        True if successful, False otherwise
    """
    print("Step 4: Saving user and tokens to database...\n")

    try:
        with get_db_context() as db:
            # Try to find existing user by email
            user = None
            if email:
                stmt = select(User).where(User.email == email)
                user = db.execute(stmt).scalar_one_or_none()

            # Create new user if not found
            if not user:
                user = User(
                    whoop_user_id=whoop_user_id or "unknown",
                    email=email,
                )
                db.add(user)
                db.flush()  # Get user ID

                print(f"✓ Created new user (ID: {user.id})")
            else:
                print(f"✓ Found existing user (ID: {user.id})")

            # Save tokens
            await token_manager.save_token(
                user_id=user.id,
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                expires_in=token_data["expires_in"],
                token_type=token_data.get("token_type", "Bearer"),
                scopes=token_data.get("scope", "").split() if token_data.get("scope") else None,
                db=db,
            )

            print(f"✓ Tokens saved for user {user.id}\n")

            # Capture user attributes while still in session context
            # (accessing them after session closes causes DetachedInstanceError)
            user_id = user.id
            user_email = user.email
            user_whoop_user_id = user.whoop_user_id

        # Now we can safely print user info after session is closed
        print("=" * 60)
        print("OAuth Setup Complete!")
        print("=" * 60 + "\n")
        print(f"User ID: {user_id}")
        print(f"Email: {user_email or 'Not provided'}")
        print(f"Whoop User ID: {user_whoop_user_id}")
        print(f"\nYou can now start the application to begin syncing data.")
        print(f"Run: python -m src.main\n")

        return True

    except Exception as e:
        print(f"\nError: Failed to save user and tokens")
        print(f"Details: {e}")
        logger.error("Failed to save OAuth tokens", error=str(e), exc_info=True)
        return False


async def main():
    """Main entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Set up OAuth authorization for Whoopster"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (for servers without a browser)",
    )
    args = parser.parse_args()

    print("\n")

    # Get optional user info
    whoop_user_id = input("Enter your Whoop User ID (optional, press Enter to skip): ").strip()
    email = input("Enter your email (optional, press Enter to skip): ").strip()

    if not whoop_user_id:
        whoop_user_id = None
    if not email:
        email = None

    # Run OAuth setup in appropriate mode
    if args.headless:
        success = await setup_oauth_headless(
            whoop_user_id=whoop_user_id,
            email=email,
        )
    else:
        success = await setup_oauth(
            whoop_user_id=whoop_user_id,
            email=email,
        )

    if success:
        sys.exit(0)
    else:
        print("\nOAuth setup failed. Please try again.\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.\n")
        sys.exit(1)
