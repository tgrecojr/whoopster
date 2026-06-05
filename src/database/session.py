"""Database session management for SQLAlchemy."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from src.config import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# Create SQLAlchemy engine with a bounded connection pool. The app fans out
# several concurrent sessions per sync; a pool caps concurrent connections
# (so a burst can't exhaust Postgres max_connections) and reuses warm
# connections instead of re-handshaking TLS/auth every session. pool_pre_ping
# validates a connection before use, so a DB restart / idle timeout is
# recovered transparently. No external pooler (PgBouncer) is in front.
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_pre_ping=True,
    echo=False,  # Set to True for SQL query logging
    future=True,  # Use SQLAlchemy 2.0 style
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """
    Get database session.

    Yields:
        Database session

    Usage:
        with get_db() as db:
            # Use db session
            pass
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database session.

    Yields:
        Database session

    Usage:
        with get_db_context() as db:
            # Use db session
            db.commit()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Database session error", error=str(e), exc_info=True)
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database.

    This function should be called after Alembic migrations have been run.
    It doesn't create tables (Alembic does that), but can be used for
    any additional initialization logic.
    """
    # Log safe connection info without credentials
    safe_host = f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    logger.info("Database initialized", host=safe_host)


def check_connection() -> bool:
    """
    Check if database connection is working.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            # SQLAlchemy 2.0 requires an executable clause, not a bare string.
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False
