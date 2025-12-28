"""Integration tests for database operations.

These tests verify database interactions, relationships, and constraints.
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from src.models.db_models import (
    User,
    OAuthToken,
    SleepRecord,
    RecoveryRecord,
    WorkoutRecord,
    CycleRecord,
    SyncStatus,
)


@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests for database operations."""

    def test_user_creation_and_retrieval(self, db_session):
        """Test creating and retrieving a user."""
        user = User(
            whoop_user_id="test_user_123",
            email="test@example.com",
        )
        db_session.add(user)
        db_session.commit()

        # Retrieve user
        retrieved = db_session.query(User).filter_by(whoop_user_id="test_user_123").first()
        assert retrieved is not None
        assert retrieved.email == "test@example.com"
        assert retrieved.created_at is not None

    def test_oauth_token_cascade_delete(self, db_session, test_user):
        """Test that OAuth tokens are deleted when user is deleted."""
        # Create token
        token = OAuthToken(
            user_id=test_user.id,
            access_token="test_token",
            refresh_token="test_refresh",
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(token)
        db_session.commit()

        token_id = token.id

        # Delete user
        db_session.delete(test_user)
        db_session.commit()

        # Token should be deleted
        deleted_token = db_session.query(OAuthToken).filter_by(id=token_id).first()
        assert deleted_token is None

    def test_sleep_record_relationships(self, db_session, test_user, test_sleep_record):
        """Test sleep record relationships."""
        db_session.refresh(test_sleep_record)

        # Access user through relationship
        assert test_sleep_record.user.id == test_user.id
        assert test_sleep_record.user.whoop_user_id == test_user.whoop_user_id

    def test_multiple_records_per_user(self, db_session, test_user):
        """Test storing multiple records for one user."""
        # Create multiple sleep records
        for i in range(5):
            record = SleepRecord(
                id=uuid4(),
                user_id=test_user.id,
                start_time=datetime.now(timezone.utc) - timedelta(days=i),
                end_time=datetime.now(timezone.utc) - timedelta(days=i) + timedelta(hours=8),
                sleep_performance_percentage=80.0 + i,
            )
            db_session.add(record)

        db_session.commit()

        # Retrieve all records
        records = db_session.query(SleepRecord).filter_by(user_id=test_user.id).all()
        assert len(records) == 5

        # Verify they have different performance values
        performances = [r.sleep_performance_percentage for r in records]
        assert len(set(performances)) == 5  # All unique

    def test_sync_status_tracking(self, db_session, test_user):
        """Test sync status tracking for different data types."""
        data_types = ["sleep", "recovery", "workout", "cycle"]

        for data_type in data_types:
            status = SyncStatus(
                user_id=test_user.id,
                data_type=data_type,
                last_sync_time=datetime.now(timezone.utc),
                status="success",
                records_fetched=10,
            )
            db_session.add(status)

        db_session.commit()

        # Retrieve all statuses
        statuses = db_session.query(SyncStatus).filter_by(user_id=test_user.id).all()
        assert len(statuses) == 4

        # Verify all data types are present
        data_types_in_db = [s.data_type for s in statuses]
        assert set(data_types_in_db) == set(data_types)

    def test_record_timestamps(self, db_session, test_user):
        """Test that record timestamps are set correctly."""
        record = SleepRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
        )
        db_session.add(record)
        db_session.commit()

        db_session.refresh(record)

        assert record.created_at is not None
        assert record.updated_at is None  # Not updated yet

        # Update record
        record.sleep_performance_percentage = 90.0
        db_session.commit()
        db_session.refresh(record)

        # updated_at should still be None (not auto-set by default)
        # Application sets it explicitly

    def test_workout_with_all_zones(self, db_session, test_user):
        """Test workout record with all heart rate zones."""
        workout = WorkoutRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            sport_name="Cycling",
            zone_zero_duration=0,
            zone_one_duration=300000,  # 5 minutes
            zone_two_duration=900000,  # 15 minutes
            zone_three_duration=1200000,  # 20 minutes
            zone_four_duration=600000,  # 10 minutes
            zone_five_duration=0,
        )
        db_session.add(workout)
        db_session.commit()

        db_session.refresh(workout)

        # Verify all zones
        total_duration = sum([
            workout.zone_zero_duration or 0,
            workout.zone_one_duration or 0,
            workout.zone_two_duration or 0,
            workout.zone_three_duration or 0,
            workout.zone_four_duration or 0,
            workout.zone_five_duration or 0,
        ])

        assert total_duration == 3000000  # 50 minutes

    def test_recovery_with_cycle_reference(self, db_session, test_user):
        """Test recovery record with cycle reference."""
        # Create cycle
        cycle = CycleRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc) - timedelta(hours=24),
            end_time=datetime.now(timezone.utc),
        )
        db_session.add(cycle)
        db_session.commit()

        # Create recovery referencing cycle
        recovery = RecoveryRecord(
            id=uuid4(),
            user_id=test_user.id,
            cycle_id=cycle.id,
            created_at_whoop=datetime.now(timezone.utc),
            recovery_score=75.0,
        )
        db_session.add(recovery)
        db_session.commit()

        db_session.refresh(recovery)

        assert recovery.cycle_id == cycle.id

    def test_jsonb_raw_data_storage(self, db_session, test_user):
        """Test storing raw JSON data."""
        raw_data = {
            "test_field": "test_value",
            "nested": {
                "field1": 123,
                "field2": [1, 2, 3],
            },
        }

        record = SleepRecord(
            id=uuid4(),
            user_id=test_user.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            raw_data=raw_data,
        )
        db_session.add(record)
        db_session.commit()

        db_session.refresh(record)

        assert record.raw_data == raw_data
        assert record.raw_data["nested"]["field1"] == 123

    def test_query_records_by_date_range(self, db_session, test_user):
        """Test querying records by date range."""
        # Use a fixed base time to avoid timing issues
        base_time = datetime.now(timezone.utc)

        # Create records over 10 days
        for i in range(10):
            record = SleepRecord(
                id=uuid4(),
                user_id=test_user.id,
                start_time=base_time - timedelta(days=i),
                end_time=base_time - timedelta(days=i) + timedelta(hours=8),
            )
            db_session.add(record)

        db_session.commit()

        # Query last 5 days
        five_days_ago = base_time - timedelta(days=5)
        records = (
            db_session.query(SleepRecord)
            .filter(SleepRecord.user_id == test_user.id)
            .filter(SleepRecord.start_time >= five_days_ago)
            .all()
        )

        assert len(records) == 6  # Days 0-5 (inclusive)

    def test_query_pending_scores(self, db_session, test_user):
        """Test querying records with pending scores."""
        # Create some scored and some pending records
        for i in range(5):
            state = "SCORED" if i % 2 == 0 else "PENDING_SCORE"
            record = SleepRecord(
                id=uuid4(),
                user_id=test_user.id,
                start_time=datetime.now(timezone.utc) - timedelta(days=i),
                end_time=datetime.now(timezone.utc) - timedelta(days=i) + timedelta(hours=8),
                score_state=state,
            )
            db_session.add(record)

        db_session.commit()

        # Query pending records
        pending = (
            db_session.query(SleepRecord)
            .filter(SleepRecord.user_id == test_user.id)
            .filter(SleepRecord.score_state == "PENDING_SCORE")
            .all()
        )

        assert len(pending) == 2

    def test_update_sync_status(self, db_session, test_user):
        """Test updating sync status."""
        # Create initial status
        status = SyncStatus(
            user_id=test_user.id,
            data_type="sleep",
            last_sync_time=datetime.now(timezone.utc) - timedelta(hours=1),
            status="success",
            records_fetched=10,
        )
        db_session.add(status)
        db_session.commit()

        status_id = status.id

        # Update status
        status.records_fetched = 20
        status.last_sync_time = datetime.now(timezone.utc)
        db_session.commit()

        # Retrieve and verify
        updated = db_session.query(SyncStatus).filter_by(id=status_id).first()
        assert updated.records_fetched == 20

    def test_multiple_users_isolated_data(self, db_session):
        """Test that data is properly isolated between users."""
        # Create two users
        user1 = User(whoop_user_id="user1", email="user1@example.com")
        user2 = User(whoop_user_id="user2", email="user2@example.com")
        db_session.add_all([user1, user2])
        db_session.commit()

        # Create records for each user
        for user in [user1, user2]:
            for i in range(3):
                record = SleepRecord(
                    id=uuid4(),
                    user_id=user.id,
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                )
                db_session.add(record)

        db_session.commit()

        # Verify each user has only their own records
        user1_records = db_session.query(SleepRecord).filter_by(user_id=user1.id).all()
        user2_records = db_session.query(SleepRecord).filter_by(user_id=user2.id).all()

        assert len(user1_records) == 3
        assert len(user2_records) == 3

        # Verify no overlap
        user1_ids = {r.id for r in user1_records}
        user2_ids = {r.id for r in user2_records}
        assert user1_ids.isdisjoint(user2_ids)
