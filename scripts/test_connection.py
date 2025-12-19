#!/usr/bin/env python3
"""Test database and API connectivity for Whoopster.

This script verifies that:
1. Database connection works
2. OAuth tokens are valid
3. Whoop API is accessible
"""

import asyncio
import sys
from typing import Dict, Any

from sqlalchemy import select, text

sys.path.insert(0, ".")

from src.config import settings
from src.database.session import get_db_context
from src.models.db_models import User, OAuthToken
from src.auth.token_manager import TokenManager
from src.api.whoop_client import WhoopClient
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def test_database_connection() -> bool:
    """
    Test database connection.

    Returns:
        True if connection successful, False otherwise
    """
    print("\n" + "=" * 60)
    print("Testing Database Connection")
    print("=" * 60 + "\n")

    try:
        with get_db_context() as db:
            # Test basic connection
            result = db.execute(text("SELECT 1")).fetchone()

            if result and result[0] == 1:
                print("✓ Database connection successful")

                # Get database info
                result = db.execute(
                    text("SELECT version()")
                ).fetchone()
                print(f"  PostgreSQL version: {result[0]}")

                # Check tables
                result = db.execute(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).fetchone()
                print(f"  Tables in database: {result[0]}")

                return True
            else:
                print("✗ Database connection failed")
                return False

    except Exception as e:
        print(f"✗ Database connection failed")
        print(f"  Error: {e}")
        return False


async def test_user_tokens() -> Dict[str, Any]:
    """
    Test user OAuth tokens.

    Returns:
        Dictionary with test results
    """
    print("\n" + "=" * 60)
    print("Testing OAuth Tokens")
    print("=" * 60 + "\n")

    results = {
        "total_users": 0,
        "users_with_tokens": 0,
        "valid_tokens": 0,
        "expired_tokens": 0,
        "users": [],
    }

    try:
        with get_db_context() as db:
            # Get all users
            stmt = select(User)
            users = db.execute(stmt).scalars().all()

            results["total_users"] = len(users)
            print(f"Found {len(users)} user(s)\n")

            if not users:
                print("  No users found. Run init_oauth.py to set up OAuth.\n")
                return results

            # Check tokens for each user
            token_manager = TokenManager()

            for user in users:
                print(f"User {user.id}:")
                print(f"  Email: {user.email or 'Not provided'}")
                print(f"  Whoop User ID: {user.whoop_user_id}")

                # Get token info
                token_info = await token_manager.get_token_info(user.id, db=db)

                if token_info:
                    results["users_with_tokens"] += 1

                    print(f"  Token type: {token_info['token_type']}")
                    print(f"  Scopes: {', '.join(token_info['scopes']) if token_info['scopes'] else 'None'}")
                    print(f"  Expires at: {token_info['expires_at']}")
                    print(f"  Seconds until expiry: {token_info['seconds_until_expiry']:.0f}")

                    if token_info["is_expired"]:
                        print(f"  Status: ✗ EXPIRED")
                        results["expired_tokens"] += 1
                    elif token_info["needs_refresh"]:
                        print(f"  Status: ⚠ Needs refresh (but valid)")
                        results["valid_tokens"] += 1
                    else:
                        print(f"  Status: ✓ Valid")
                        results["valid_tokens"] += 1

                    results["users"].append({
                        "user_id": user.id,
                        "has_token": True,
                        "is_expired": token_info["is_expired"],
                    })
                else:
                    print(f"  Status: ✗ No token found")
                    results["users"].append({
                        "user_id": user.id,
                        "has_token": False,
                        "is_expired": None,
                    })

                print()

        return results

    except Exception as e:
        print(f"✗ Token check failed")
        print(f"  Error: {e}")
        logger.error("Token check failed", error=str(e), exc_info=True)
        return results


async def test_whoop_api(user_id: int) -> bool:
    """
    Test Whoop API connectivity.

    Args:
        user_id: User ID to test

    Returns:
        True if API accessible, False otherwise
    """
    print("=" * 60)
    print(f"Testing Whoop API for User {user_id}")
    print("=" * 60 + "\n")

    try:
        # Create client
        client = WhoopClient(user_id=user_id)

        # Test API by fetching user profile
        print("Fetching user profile...")
        profile = await client.get_user_profile()

        print("✓ API connection successful")
        print(f"  User ID: {profile.get('user_id', 'Unknown')}")
        print(f"  First name: {profile.get('first_name', 'Unknown')}")
        print(f"  Last name: {profile.get('last_name', 'Unknown')}")
        print()

        return True

    except Exception as e:
        print(f"✗ API connection failed")
        print(f"  Error: {e}")
        logger.error("API test failed", error=str(e), exc_info=True)
        print()
        return False


async def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("Whoopster Connection Test")
    print("=" * 60)

    all_passed = True

    # Test 1: Database Connection
    db_success = test_database_connection()
    all_passed = all_passed and db_success

    if not db_success:
        print("\n✗ Database connection failed. Fix database issues before continuing.\n")
        sys.exit(1)

    # Test 2: User Tokens
    token_results = await test_user_tokens()

    if token_results["total_users"] == 0:
        print("⚠ No users found. Run scripts/init_oauth.py to set up OAuth.\n")
        sys.exit(0)

    if token_results["valid_tokens"] == 0:
        print("✗ No valid tokens found. Run scripts/init_oauth.py to authorize.\n")
        sys.exit(1)

    # Test 3: Whoop API (for users with valid tokens)
    print("\n")
    api_tested = False

    for user_data in token_results["users"]:
        if user_data["has_token"] and not user_data["is_expired"]:
            api_success = await test_whoop_api(user_data["user_id"])
            all_passed = all_passed and api_success
            api_tested = True
            break  # Only test one user

    if not api_tested:
        print("⚠ Skipped API test (no valid tokens)\n")

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60 + "\n")

    print(f"Database: {'✓ OK' if db_success else '✗ Failed'}")
    print(f"Users: {token_results['total_users']}")
    print(f"Valid tokens: {token_results['valid_tokens']}")
    print(f"Expired tokens: {token_results['expired_tokens']}")

    if all_passed and api_tested:
        print("\n✓ All tests passed! System is ready.\n")
        sys.exit(0)
    elif all_passed:
        print("\n⚠ Database and tokens OK, but API not tested.\n")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed. Please review errors above.\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.\n")
        sys.exit(1)
