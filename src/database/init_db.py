"""Database initialization and migration management."""

import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from src.config import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def verify_database_connection() -> bool:
    """
    Verify database is accessible.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        logger.info("Database connection verified", database=settings.postgres_db)
        return True
    except OperationalError as e:
        logger.error(
            "Database connection failed",
            database=settings.postgres_db,
            host=settings.postgres_host,
            error=str(e)
        )
        return False
    except Exception as e:
        logger.error(
            "Unexpected error verifying database connection",
            error=str(e),
            exc_info=True
        )
        return False


def run_migrations() -> bool:
    """
    Run all pending Alembic migrations.

    Returns:
        True if migrations successful, False otherwise
    """
    try:
        logger.info("Running database migrations...")

        # Run alembic upgrade head
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,  # Project root
        )

        logger.info(
            "Migrations completed successfully",
            stdout=result.stdout.strip() if result.stdout else None
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(
            "Migration failed",
            returncode=e.returncode,
            stderr=e.stderr,
            stdout=e.stdout
        )
        return False
    except FileNotFoundError:
        logger.error("Alembic command not found. Is it installed?")
        return False
    except Exception as e:
        logger.error("Unexpected error running migrations", error=str(e), exc_info=True)
        return False


def check_migration_status() -> dict:
    """
    Check current migration status.

    Returns:
        Dictionary with migration status information
    """
    try:
        # Get current migration version
        result = subprocess.run(
            ["alembic", "current"],
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        current_version = result.stdout.strip()

        # Get pending migrations
        result = subprocess.run(
            ["alembic", "heads"],
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        target_version = result.stdout.strip()

        return {
            "current": current_version,
            "target": target_version,
            "up_to_date": current_version == target_version
        }
    except Exception as e:
        logger.error("Failed to check migration status", error=str(e))
        return {"error": str(e)}


def init_database() -> bool:
    """
    Initialize database with migrations.

    This is the main entry point for database initialization.
    It verifies connection and runs all pending migrations.

    Returns:
        True if initialization successful, False otherwise
    """
    logger.info("Initializing database...")

    # Verify database connection
    if not verify_database_connection():
        logger.error("Cannot connect to database. Initialization failed.")
        return False

    # Run migrations
    if not run_migrations():
        logger.error("Migrations failed. Initialization failed.")
        return False

    # Check migration status
    status = check_migration_status()
    logger.info("Migration status", **status)

    logger.info("Database initialization complete")
    return True


if __name__ == "__main__":
    """Run database initialization when executed directly."""
    success = init_database()
    sys.exit(0 if success else 1)
