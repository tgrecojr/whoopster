#!/usr/bin/env python3
"""
Backfill historical Whoop data.

This script allows you to fetch historical data from Whoop by specifying
a date range. Useful for:
- Initial setup to fetch all historical data
- Filling gaps in data due to sync failures
- Re-syncing data from a specific time period

Usage:
    # Backfill all data from last 30 days
    python -m scripts.backfill_data --days 30

    # Backfill specific date range
    python -m scripts.backfill_data --start 2024-01-01 --end 2024-12-31

    # Backfill only specific data types
    python -m scripts.backfill_data --days 90 --types sleep recovery

    # Backfill all available historical data (can take a while!)
    python -m scripts.backfill_data --all

Examples:
    # Get last 6 months of data
    python -m scripts.backfill_data --days 180

    # Get data from specific month
    python -m scripts.backfill_data --start 2024-06-01 --end 2024-06-30

    # Get only sleep and workout data from last year
    python -m scripts.backfill_data --days 365 --types sleep workout
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.data_collector import DataCollector
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill historical Whoop data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Date range options
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        "--days",
        type=int,
        help="Number of days to backfill from today (e.g., 30, 90, 365)",
    )
    date_group.add_argument(
        "--all",
        action="store_true",
        help="Backfill all available historical data (no start date limit)",
    )
    date_group.add_argument(
        "--start",
        type=str,
        help="Start date in YYYY-MM-DD format (requires --end)",
    )

    parser.add_argument(
        "--end",
        type=str,
        help="End date in YYYY-MM-DD format (optional, defaults to today)",
    )

    parser.add_argument(
        "--types",
        nargs="+",
        choices=["sleep", "recovery", "workout", "cycle"],
        help="Specific data types to sync (default: all types)",
    )

    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        help="User ID to sync data for (default: 1)",
    )

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    """
    Parse date string to datetime object.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Datetime object in UTC timezone

    Raises:
        ValueError: If date format is invalid
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise ValueError(
            f"Invalid date format: {date_str}. Use YYYY-MM-DD format."
        ) from e


async def backfill_data(
    user_id: int,
    start: Optional[datetime],
    end: Optional[datetime],
    data_types: Optional[List[str]],
) -> None:
    """
    Backfill historical data for a user.

    Args:
        user_id: Database user ID
        start: Start date for backfill (None = no limit)
        end: End date for backfill (None = today)
        data_types: List of data types to sync (None = all)
    """
    # Check if user exists and has OAuth tokens
    from src.database.session import get_db_context
    from src.models.db_models import User, OAuthToken
    from sqlalchemy import select

    with get_db_context() as db:
        # Check if user exists
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()

        if user is None:
            print("\n" + "=" * 70)
            print("❌ ERROR: User Not Found")
            print("=" * 70)
            print(f"User ID {user_id} does not exist in the database.")
            print("\nYou must run OAuth setup first to create a user and authorize Whoop access:")
            print("\n  docker-compose exec app python scripts/init_oauth.py")
            print("\nThis will:")
            print("  1. Create a user record in the database")
            print("  2. Open your browser to authorize Whoop access")
            print("  3. Store OAuth tokens securely")
            print("\nAfter OAuth setup completes, you can run the backfill script.")
            print("=" * 70 + "\n")
            return

        # Check if OAuth tokens exist
        oauth_token = db.execute(
            select(OAuthToken).where(OAuthToken.user_id == user_id)
        ).scalar_one_or_none()

        if oauth_token is None:
            print("\n" + "=" * 70)
            print("❌ ERROR: No OAuth Tokens Found")
            print("=" * 70)
            print(f"User ID {user_id} exists but has no OAuth tokens.")
            print("\nYou must authorize Whoop access first:")
            print("\n  docker-compose exec app python scripts/init_oauth.py")
            print("\nThis will open your browser to authorize access to your Whoop data.")
            print("=" * 70 + "\n")
            return

    # Default end date to now if not specified
    if end is None:
        end = datetime.now(timezone.utc)

    logger.info(
        "Starting historical data backfill",
        user_id=user_id,
        start=start.isoformat() if start else "No limit (all history)",
        end=end.isoformat(),
        data_types=data_types or "all",
    )

    print("\n" + "=" * 70)
    print("HISTORICAL DATA BACKFILL")
    print("=" * 70)
    print(f"User ID: {user_id}")
    print(f"Start Date: {start.strftime('%Y-%m-%d') if start else 'All available history'}")
    print(f"End Date: {end.strftime('%Y-%m-%d')}")
    print(f"Data Types: {', '.join(data_types) if data_types else 'All (sleep, recovery, workout, cycle)'}")
    print("=" * 70)

    if not start:
        print("\n⚠️  WARNING: Fetching ALL historical data may take a long time!")
        print("    Whoop stores your complete history since you started using the device.")
        response = input("\nContinue? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Backfill cancelled.")
            return

    print("\n🔄 Starting backfill...\n")

    try:
        # Initialize data collector
        collector = DataCollector(user_id=user_id)

        # Run backfill
        results = await collector.sync_all_data(
            start=start,
            end=end,
            data_types=data_types,
        )

        # Display results
        print("\n" + "=" * 70)
        print("BACKFILL COMPLETE")
        print("=" * 70)
        print(f"Total Records Synced: {results['total_records']}")
        print(f"Total Errors: {results['total_errors']}")
        print("\nResults by Data Type:")

        for data_type, result in results["results"].items():
            status_icon = "✅" if result["status"] == "success" else "❌"
            print(f"  {status_icon} {data_type.capitalize()}: {result.get('records_synced', 0)} records")
            if result["status"] == "error":
                print(f"     Error: {result.get('error', 'Unknown error')}")

        print("=" * 70 + "\n")

        if results["total_errors"] > 0:
            logger.warning(
                "Backfill completed with errors",
                total_records=results["total_records"],
                total_errors=results["total_errors"],
            )
        else:
            logger.info(
                "Backfill completed successfully",
                total_records=results["total_records"],
            )

    except Exception as e:
        logger.error(
            "Backfill failed",
            error=str(e),
            exc_info=True,
        )
        print(f"\n❌ Error: {e}")
        print("\nCheck application logs for details.")
        raise


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Determine start and end dates
    start = None
    end = None

    if args.days:
        # Calculate start date from days ago
        start = datetime.now(timezone.utc) - timedelta(days=args.days)
        logger.info(f"Backfilling last {args.days} days")

    elif args.all:
        # No start date = fetch all history
        start = None
        logger.info("Backfilling all available historical data")

    elif args.start:
        # Parse start date
        start = parse_date(args.start)

        # Parse end date if provided
        if args.end:
            end = parse_date(args.end)

        # Validate date range
        if end and start > end:
            print("Error: Start date must be before end date")
            return

    # Run backfill
    try:
        asyncio.run(
            backfill_data(
                user_id=args.user_id,
                start=start,
                end=end,
                data_types=args.types,
            )
        )
    except KeyboardInterrupt:
        print("\n\nBackfill cancelled by user.")
    except Exception as e:
        print(f"\nBackfill failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()
