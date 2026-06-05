"""Tests for database session helpers."""

import pytest
from sqlalchemy import create_engine

import src.database.session as session_module


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
