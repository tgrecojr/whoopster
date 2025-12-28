"""Pytest configuration and fixtures for Whoopster tests."""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Generator, AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from faker import Faker

from src.models.db_models import Base, User, OAuthToken, SleepRecord, RecoveryRecord, WorkoutRecord, CycleRecord
from src.config import settings
from src.auth.encryption import get_token_encryption

# Initialize Faker
fake = Faker()


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def database_url() -> str:
    """Get test database URL."""
    return "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine(database_url):
    """Create test database engine."""
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign keys for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Drop all tables
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Create a new database session for a test."""
    connection = engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ============================================================================
# Model Fixtures
# ============================================================================

@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        whoop_user_id=str(uuid4()),
        email=fake.email(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_oauth_token(db_session: Session, test_user: User) -> OAuthToken:
    """Create a test OAuth token."""
    encryption = get_token_encryption()
    plaintext_access = fake.uuid4()
    plaintext_refresh = fake.uuid4()

    token = OAuthToken(
        user_id=test_user.id,
        access_token=encryption.encrypt(plaintext_access),
        refresh_token=encryption.encrypt(plaintext_refresh),
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["read:sleep", "read:workout", "read:recovery", "read:cycles"],
    )
    # Store plaintext values as attributes for test assertions
    token._plaintext_access_token = plaintext_access
    token._plaintext_refresh_token = plaintext_refresh

    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)
    return token


@pytest.fixture
def expired_oauth_token(db_session: Session, test_user: User) -> OAuthToken:
    """Create an expired OAuth token."""
    encryption = get_token_encryption()
    plaintext_access = fake.uuid4()
    plaintext_refresh = fake.uuid4()

    token = OAuthToken(
        user_id=test_user.id,
        access_token=encryption.encrypt(plaintext_access),
        refresh_token=encryption.encrypt(plaintext_refresh),
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        scopes=["read:sleep", "read:workout", "read:recovery", "read:cycles"],
    )
    # Store plaintext values as attributes for test assertions
    token._plaintext_access_token = plaintext_access
    token._plaintext_refresh_token = plaintext_refresh

    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)
    return token


@pytest.fixture
def test_sleep_record(db_session: Session, test_user: User) -> SleepRecord:
    """Create a test sleep record."""
    record = SleepRecord(
        id=uuid4(),
        user_id=test_user.id,
        start_time=datetime.now(timezone.utc) - timedelta(hours=8),
        end_time=datetime.now(timezone.utc),
        timezone_offset="-05:00",
        light_sleep_duration=180000,  # 3 hours in ms
        slow_wave_sleep_duration=120000,  # 2 hours in ms
        rem_sleep_duration=60000,  # 1 hour in ms
        awake_duration=30000,  # 30 minutes in ms
        sleep_performance_percentage=85.5,
        sleep_consistency_percentage=90.0,
        respiratory_rate=14.5,
        sleep_efficiency=95.0,
        score_state="SCORED",
        is_nap=False,
        raw_data={"test": "data"},
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.fixture
def test_recovery_record(db_session: Session, test_user: User) -> RecoveryRecord:
    """Create a test recovery record."""
    record = RecoveryRecord(
        id=uuid4(),
        user_id=test_user.id,
        cycle_id=uuid4(),
        created_at_whoop=datetime.now(timezone.utc),
        recovery_score=75.0,
        resting_heart_rate=55,
        hrv_rmssd=65.5,
        spo2_percentage=97.5,
        skin_temp_celsius=33.2,
        score_state="SCORED",
        calibrating=False,
        raw_data={"test": "data"},
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.fixture
def test_workout_record(db_session: Session, test_user: User) -> WorkoutRecord:
    """Create a test workout record."""
    record = WorkoutRecord(
        id=uuid4(),
        user_id=test_user.id,
        start_time=datetime.now(timezone.utc) - timedelta(hours=1),
        end_time=datetime.now(timezone.utc),
        timezone_offset="-05:00",
        sport_id=1,
        sport_name="Running",
        strain_score=12.5,
        average_heart_rate=150,
        max_heart_rate=180,
        kilojoules=500.0,
        distance_meters=5000.0,
        altitude_gain_meters=50.0,
        altitude_change_meters=10.0,
        zone_zero_duration=0,
        zone_one_duration=600000,
        zone_two_duration=1800000,
        zone_three_duration=900000,
        zone_four_duration=300000,
        zone_five_duration=0,
        score_state="SCORED",
        raw_data={"test": "data"},
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.fixture
def test_cycle_record(db_session: Session, test_user: User) -> CycleRecord:
    """Create a test cycle record."""
    record = CycleRecord(
        id=uuid4(),
        user_id=test_user.id,
        start_time=datetime.now(timezone.utc) - timedelta(hours=24),
        end_time=datetime.now(timezone.utc),
        timezone_offset="-05:00",
        strain_score=14.5,
        kilojoules=2000.0,
        average_heart_rate=65,
        max_heart_rate=180,
        score_state="SCORED",
        raw_data={"test": "data"},
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


# ============================================================================
# API Mock Data
# ============================================================================

@pytest.fixture
def mock_whoop_sleep_response() -> dict:
    """Mock Whoop API sleep response."""
    return {
        "records": [
            {
                "id": str(uuid4()),
                "start": "2025-12-18T00:00:00.000Z",
                "end": "2025-12-18T08:00:00.000Z",
                "timezone_offset": "-05:00",
                "nap": False,
                "score_state": "SCORED",
                "score": {
                    "stage_summary": {
                        "total_light_sleep_time_milli": 180000,
                        "total_slow_wave_sleep_time_milli": 120000,
                        "total_rem_sleep_time_milli": 60000,
                        "total_awake_time_milli": 30000,
                    },
                    "sleep_performance_percentage": 85.5,
                    "sleep_consistency_percentage": 90.0,
                    "respiratory_rate": 14.5,
                    "sleep_efficiency_percentage": 95.0,
                },
            }
        ],
        "next_token": None,
    }


@pytest.fixture
def mock_whoop_recovery_response() -> dict:
    """Mock Whoop API recovery response."""
    return {
        "records": [
            {
                "id": str(uuid4()),
                "cycle_id": str(uuid4()),
                "created_at": "2025-12-18T08:00:00.000Z",
                "score_state": "SCORED",
                "score": {
                    "recovery_score": 75.0,
                    "resting_heart_rate": 55,
                    "hrv_rmssd_milli": 65.5,
                    "spo2_percentage": 97.5,
                    "skin_temp_celsius": 33.2,
                    "calibrating": False,
                },
            }
        ],
        "next_token": None,
    }


@pytest.fixture
def mock_whoop_workout_response() -> dict:
    """Mock Whoop API workout response."""
    return {
        "records": [
            {
                "id": str(uuid4()),
                "start": "2025-12-18T10:00:00.000Z",
                "end": "2025-12-18T11:00:00.000Z",
                "timezone_offset": "-05:00",
                "sport_id": 1,
                "sport_name": "Running",
                "score_state": "SCORED",
                "score": {
                    "strain": 12.5,
                    "average_heart_rate": 150,
                    "max_heart_rate": 180,
                    "kilojoule": 500.0,
                    "distance_meter": 5000.0,
                    "altitude_gain_meter": 50.0,
                    "altitude_change_meter": 10.0,
                    "zone_duration": {
                        "zone_zero_milli": 0,
                        "zone_one_milli": 600000,
                        "zone_two_milli": 1800000,
                        "zone_three_milli": 900000,
                        "zone_four_milli": 300000,
                        "zone_five_milli": 0,
                    },
                },
            }
        ],
        "next_token": None,
    }


@pytest.fixture
def mock_whoop_cycle_response() -> dict:
    """Mock Whoop API cycle response."""
    return {
        "records": [
            {
                "id": str(uuid4()),
                "start": "2025-12-17T00:00:00.000Z",
                "end": "2025-12-18T00:00:00.000Z",
                "timezone_offset": "-05:00",
                "score_state": "SCORED",
                "score": {
                    "strain": 14.5,
                    "kilojoule": 2000.0,
                    "average_heart_rate": 65,
                    "max_heart_rate": 180,
                },
            }
        ],
        "next_token": None,
    }


@pytest.fixture
def mock_whoop_user_profile() -> dict:
    """Mock Whoop API user profile response."""
    return {
        "user_id": str(uuid4()),
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
    }


# ============================================================================
# Async Fixtures
# ============================================================================

@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Time Fixtures
# ============================================================================

@pytest.fixture
def fixed_datetime():
    """Provide a fixed datetime for testing."""
    return datetime(2025, 12, 18, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def date_range():
    """Provide a date range for testing."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    return start, end
