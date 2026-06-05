"""Tests for database session helpers."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

import src.database.session as session_module
from src.config import settings


@pytest.mark.unit
def test_check_connection_succeeds(monkeypatch):
    """check_connection must run a real, executable statement.

    Regression: it previously passed a bare ``"SELECT 1"`` string, which raises
    under SQLAlchemy 2.0 and made the function always return False.
    """
    test_engine = create_engine("sqlite://")
    monkeypatch.setattr(session_module, "engine", test_engine)

    assert session_module.check_connection() is True


@pytest.mark.unit
def test_check_connection_failure_returns_false(monkeypatch):
    """A broken connection is reported as False, not raised."""
    # Point at an unreachable driver target so connect() fails fast.
    bad_engine = create_engine("sqlite:////nonexistent/path/does/not/exist.db")
    monkeypatch.setattr(session_module, "engine", bad_engine)

    assert session_module.check_connection() is False


@pytest.mark.unit
def test_engine_uses_bounded_pool_with_pre_ping():
    """The production engine must use a bounded QueuePool with pre-ping on.

    Inspecting the pool does not open a connection, so this is safe without a
    live database.
    """
    pool = session_module.engine.pool

    assert isinstance(pool, QueuePool)
    assert pool._pre_ping is True
    assert pool.size() == settings.db_pool_size
    assert pool._max_overflow == settings.db_max_overflow
    assert pool._recycle == settings.db_pool_recycle_seconds
