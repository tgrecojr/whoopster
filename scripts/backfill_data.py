#!/usr/bin/env python3
"""Backfill raw Whoop data into the bronze layer for a date range.

Use this to "true up" gaps in bronze between two dates. It fetches the requested
range from the Whoop API; the raw responses are captured to the bronze layer at
the HTTP-client level. NOTHING is written to the database -- this is a
bronze-only tool.

It is safe to run on a server whose container is already running the regular
poller: a shared advisory file lock (src/utils/sync_lock.py) ensures the poller
and this backfill never call the API at the same time, so the per-process rate
limiter keeps you under the Whoop API limit. This backfill waits for any
in-flight poll to finish, then holds the lock (the poller skips its cycle) until
it completes.

Bronze capture must be enabled (BRONZE_ROOT set, with a persistent volume
mounted at that path) or this tool has nothing to write and exits with an error.

Usage (typically via `docker exec` into the already-running container, so the
env vars and bronze volume are inherited):

    docker exec <container> python -m scripts.backfill_data --start 2025-12-17
    docker exec <container> python -m scripts.backfill_data --start 2025-12-17 --end 2026-01-15
    docker exec <container> python -m scripts.backfill_data --days 30
    docker exec <container> python -m scripts.backfill_data --start 2025-12-17 --types sleep recovery

Only range-based data types can be backfilled (sleep, recovery, workout, cycle);
profile and body measurement are current-snapshot endpoints with no date range.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.api.whoop_client import WhoopClient
from src.auth.token_manager import TokenManager
from src.bronze import is_bronze_enabled
from src.utils.logging_config import get_logger
from src.utils.sync_lock import SyncLockTimeout, sync_lock

logger = get_logger(__name__)

# Range-based collections only. Current-snapshot endpoints (profile, body
# measurement) have no date range and so cannot be "backfilled".
RANGE_DATA_TYPES = ["sleep", "recovery", "workout", "cycle"]

# Maps a data type to the WhoopClient method that fetches (and, via the client,
# bronze-captures) its records for a date range.
_FETCHERS = {
    "sleep": "get_sleep_records",
    "recovery": "get_recovery_records",
    "workout": "get_workout_records",
    "cycle": "get_cycle_records",
}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill raw Whoop data into the bronze layer for a date range",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        "--days",
        type=int,
        help="Backfill from N days ago through now (e.g., 30, 90)",
    )
    date_group.add_argument(
        "--start",
        type=str,
        help="Start date in YYYY-MM-DD format (end defaults to now)",
    )

    parser.add_argument(
        "--end",
        type=str,
        help="End date in YYYY-MM-DD format (optional, defaults to now)",
    )
    parser.add_argument(
        "--types",
        nargs="+",
        choices=RANGE_DATA_TYPES,
        help=f"Data types to backfill (default: {', '.join(RANGE_DATA_TYPES)})",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        help="User ID to backfill data for (default: 1)",
    )

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    """Parse a YYYY-MM-DD string to a UTC datetime."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise ValueError(
            f"Invalid date format: {date_str}. Use YYYY-MM-DD format."
        ) from e


async def fetch_range_to_bronze(
    client: WhoopClient,
    start: datetime,
    end: datetime,
    data_types: List[str],
) -> Dict[str, int]:
    """Fetch each data type over [start, end]; raw pages are captured to bronze.

    Records are fetched only to drive capture (which happens at the HTTP-client
    level) and to count them; nothing is written to the database.

    Returns:
        Mapping of data type -> number of records fetched.
    """
    totals: Dict[str, int] = {}
    for data_type in data_types:
        fetch = getattr(client, _FETCHERS[data_type])
        records = await fetch(start=start, end=end)
        totals[data_type] = len(records)
        logger.info(
            "Backfilled type to bronze",
            data_type=data_type,
            count=len(records),
        )
    return totals


async def backfill_bronze(
    user_id: int,
    start: datetime,
    end: datetime,
    data_types: List[str],
) -> int:
    """Run the bronze backfill. Returns a process exit code (0 = success)."""
    # Fail fast if the user has no usable token, before holding the lock.
    token_manager = TokenManager()
    if not await token_manager.get_valid_token(user_id):
        print(f"\n❌ ERROR: user {user_id} has no valid Whoop OAuth token.")
        print("   Authorize first (scripts/init_oauth.py), then retry.\n")
        return 1

    client = WhoopClient(user_id=user_id, token_manager=token_manager)
    try:
        totals = await fetch_range_to_bronze(client, start, end, data_types)
    finally:
        await client.aclose()

    print("\n" + "=" * 70)
    print("BRONZE BACKFILL COMPLETE")
    print("=" * 70)
    total = 0
    for data_type in data_types:
        count = totals.get(data_type, 0)
        total += count
        print(f"  ✅ {data_type.capitalize()}: {count} records captured")
    print(f"\nTotal records captured to bronze: {total}")
    print("=" * 70 + "\n")
    logger.info("Bronze backfill completed", user_id=user_id, total_records=total)
    return 0


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Resolve the date range.
    now = datetime.now(timezone.utc)
    if args.days is not None:
        start, end = now - timedelta(days=args.days), now
    else:
        start = parse_date(args.start)
        end = parse_date(args.end) if args.end else now

    if start > end:
        print("Error: start date must be before end date")
        sys.exit(1)

    data_types = args.types or RANGE_DATA_TYPES

    # Bronze must be enabled, or there is nothing to write. Check before taking
    # the lock so a misconfigured run fails instantly.
    if not is_bronze_enabled():
        print("\n❌ ERROR: bronze capture is disabled (BRONZE_ROOT not set).")
        print("   Set BRONZE_ROOT (and mount a persistent volume there), then retry.\n")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("BRONZE BACKFILL")
    print("=" * 70)
    print(f"User ID:    {args.user_id}")
    print(f"Start:      {start.strftime('%Y-%m-%d')}")
    print(f"End:        {end.strftime('%Y-%m-%d')}")
    print(f"Data Types: {', '.join(data_types)}")
    print("=" * 70)
    print("\n🔒 Acquiring sync lock (waiting for any in-flight poll to finish)...")

    try:
        # Hold the lock for the whole backfill so the poller skips its cycles.
        # Acquired synchronously (outside the event loop) so the blocking wait
        # never stalls async work.
        with sync_lock(blocking=True):
            print("🔄 Lock acquired. Starting backfill...\n")
            exit_code = asyncio.run(
                backfill_bronze(args.user_id, start, end, data_types)
            )
    except SyncLockTimeout as e:
        print(f"\n❌ ERROR: {e}")
        print("   A poll/backfill is already running. Try again shortly.\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nBackfill cancelled by user.")
        sys.exit(130)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
