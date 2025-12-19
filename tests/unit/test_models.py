"""Tests for database models."""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy.exc import IntegrityError

from src.models.db_models import User, OAuthToken, SleepRecord, RecoveryRecord, WorkoutRecord, CycleRecord, SyncStatus


@pytest.mark.unit
class TestUserModel:
    """Tests for User model."""

    def test_create_user(self, db_session):
        """Test creating a user."""
        user = User(
            whoop_user_id="test_whoop_id",
            email="test@example.com",
        )
        db_session.add(user)
        db_session.commit()

        assert user.id is not None
        assert user.whoop_user_id == "test_whoop_id"
        assert user.email == "test@example.com"
        assert user.created_at is not None
        assert user.updated_at is None

    def test_user_unique_whoop_id(self, db_session):
        """Test that whoop_user_id must be unique."""
        user1 = User(whoop_user_id="test_id", email="user1@example.com")
        db_session.add(user1)
        db_session.commit()

        user2 = User(whoop_user_id="test_id", email="user2@example.com")
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_user_nullable_email(self, db_session):
        """Test that email is nullable."""
        user = User(whoop_user_id="test_id")
        db_session.add(user)
        db_session.commit()

        assert user.email is None

    def test_user_relationships(self, test_user, test_oauth_token, db_session):
        """Test user relationships."""
        db_session.refresh(test_user)

        assert len(test_user.oauth_tokens) == 1
        assert test_user.oauth_tokens[0].id == test_oauth_token.id


@pytest.mark.unit
class TestOAuthTokenModel:
    """Tests for OAuthToken model."""

    def test_create_oauth_token(self, db_session, test_user):
        """Test creating an OAuth token."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=1)

        token = OAuthToken(
            user_id=test_user.id,
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            token_type="Bearer",
            expires_at=expires_at,
            scopes=["read:sleep", "read:workout"],
        )
        db_session.add(token)
        db_session.commit()
        db_session.refresh(token)

        assert token.id is not None
        assert token.user_id == test_user.id
        assert token.access_token == "test_access_token"
        assert token.refresh_token == "test_refresh_token"
        assert token.scopes == ["read:sleep", "read:workout"]
        # SQLite may strip timezone info, so compare as naive if needed
        token_time = token.expires_at.replace(tzinfo=None) if token.expires_at.tzinfo is None else token.expires_at
        now_time = now.replace(tzinfo=None) if token.expires_at.tzinfo is None else now
        assert token_time > now_time

    def test_token_cascade_delete(self, db_session, test_user, test_oauth_token):
        """Test that tokens are deleted when user is deleted."""
        token_id = test_oauth_token.id

        db_session.delete(test_user)
        db_session.commit()

        deleted_token = db_session.query(OAuthToken).filter_by(id=token_id).first()
        assert deleted_token is None


@pytest.mark.unit
class TestSleepRecordModel:
    """Tests for SleepRecord model."""

    def test_create_sleep_record(self, db_session, test_user):
        """Test creating a sleep record."""
        record = SleepRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc) - timedelta(hours=8),
            end_time=datetime.now(timezone.utc),
            timezone_offset="-05:00",
            sleep_performance_percentage=85.5,
            raw_data={"test": "data"},
        )
        db_session.add(record)
        db_session.commit()

        assert record.id is not None
        assert record.user_id == test_user.id
        assert record.sleep_performance_percentage == 85.5

    def test_sleep_record_nullable_fields(self, db_session, test_user):
        """Test that score fields are nullable."""
        record = SleepRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
        )
        db_session.add(record)
        db_session.commit()

        assert record.sleep_performance_percentage is None
        assert record.light_sleep_duration is None


@pytest.mark.unit
class TestRecoveryRecordModel:
    """Tests for RecoveryRecord model."""

    def test_create_recovery_record(self, db_session, test_user):
        """Test creating a recovery record."""
        record = RecoveryRecord(
            id=uuid4(),
            user_id=test_user.id,
            created_at_whoop=datetime.now(timezone.utc),
            recovery_score=75.0,
            resting_heart_rate=55,
            hrv_rmssd=65.5,
            raw_data={"test": "data"},
        )
        db_session.add(record)
        db_session.commit()

        assert record.id is not None
        assert record.recovery_score == 75.0
        assert record.hrv_rmssd == 65.5

    def test_recovery_record_nullable_cycle_id(self, db_session, test_user):
        """Test that cycle_id is nullable."""
        record = RecoveryRecord(
            id=uuid4(),
            user_id=test_user.id,
            created_at_whoop=datetime.now(timezone.utc),
        )
        db_session.add(record)
        db_session.commit()

        assert record.cycle_id is None


@pytest.mark.unit
class TestWorkoutRecordModel:
    """Tests for WorkoutRecord model."""

    def test_create_workout_record(self, db_session, test_user):
        """Test creating a workout record."""
        record = WorkoutRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
            sport_id=1,
            sport_name="Running",
            strain_score=12.5,
            average_heart_rate=150,
            max_heart_rate=180,
            raw_data={"test": "data"},
        )
        db_session.add(record)
        db_session.commit()

        assert record.id is not None
        assert record.sport_name == "Running"
        assert record.strain_score == 12.5

    def test_workout_zone_durations(self, db_session, test_user):
        """Test workout zone duration fields."""
        record = WorkoutRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            zone_zero_duration=0,
            zone_one_duration=600000,
            zone_two_duration=1800000,
            zone_three_duration=900000,
            zone_four_duration=300000,
            zone_five_duration=0,
        )
        db_session.add(record)
        db_session.commit()

        assert record.zone_two_duration == 1800000
        assert record.zone_five_duration == 0


@pytest.mark.unit
class TestCycleRecordModel:
    """Tests for CycleRecord model."""

    def test_create_cycle_record(self, db_session, test_user):
        """Test creating a cycle record."""
        record = CycleRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc) - timedelta(hours=24),
            end_time=datetime.now(timezone.utc),
            strain_score=14.5,
            kilojoules=2000.0,
            raw_data={"test": "data"},
        )
        db_session.add(record)
        db_session.commit()

        assert record.id is not None
        assert record.strain_score == 14.5
        assert record.kilojoules == 2000.0


@pytest.mark.unit
class TestSyncStatusModel:
    """Tests for SyncStatus model."""

    def test_create_sync_status(self, db_session, test_user):
        """Test creating a sync status record."""
        status = SyncStatus(
            user_id=test_user.id,
            data_type="sleep",
            last_sync_time=datetime.now(timezone.utc),
            status="success",
            records_fetched=10,
        )
        db_session.add(status)
        db_session.commit()

        assert status.id is not None
        assert status.data_type == "sleep"
        assert status.status == "success"
        assert status.records_fetched == 10

    def test_sync_status_error_message(self, db_session, test_user):
        """Test sync status with error message."""
        status = SyncStatus(
            user_id=test_user.id,
            data_type="workout",
            last_sync_time=datetime.now(timezone.utc),
            status="error",
            error_message="API connection failed",
        )
        db_session.add(status)
        db_session.commit()

        assert status.status == "error"
        assert status.error_message == "API connection failed"
