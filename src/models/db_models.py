"""SQLAlchemy database models for Whoopster application."""

from datetime import datetime
from typing import Optional, List, Any
import uuid
import json

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Numeric,
    Text,
    ARRAY,
    ForeignKey,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class StringArray(TypeDecorator):
    """Array type that works with both PostgreSQL and SQLite.

    Uses ARRAY in PostgreSQL and JSON in SQLite/other databases.
    """
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(ARRAY(Text))
        else:
            return dialect.type_descriptor(Text)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql':
            return value
        else:
            return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql':
            return value
        else:
            return json.loads(value)


class JSONType(TypeDecorator):
    """JSON type that works with both PostgreSQL and SQLite.

    Uses JSONB in PostgreSQL and TEXT (with JSON) in SQLite/other databases.
    """
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB)
        else:
            return dialect.type_descriptor(Text)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql':
            return value
        else:
            return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, str):
                return json.loads(value)
            return value


class User(Base):
    """User model for multi-user support."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    whoop_user_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    oauth_tokens = relationship(
        "OAuthToken", back_populates="user", cascade="all, delete-orphan"
    )
    sleep_records = relationship(
        "SleepRecord", back_populates="user", cascade="all, delete-orphan"
    )
    recovery_records = relationship(
        "RecoveryRecord", back_populates="user", cascade="all, delete-orphan"
    )
    workout_records = relationship(
        "WorkoutRecord", back_populates="user", cascade="all, delete-orphan"
    )
    cycle_records = relationship(
        "CycleRecord", back_populates="user", cascade="all, delete-orphan"
    )
    sync_statuses = relationship(
        "SyncStatus", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, whoop_user_id='{self.whoop_user_id}')>"


class OAuthToken(Base):
    """OAuth token storage for secure authentication."""

    __tablename__ = "oauth_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_type = Column(String(50), default="Bearer")
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    scopes = Column(StringArray)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="oauth_tokens")

    def __repr__(self) -> str:
        return f"<OAuthToken(user_id={self.user_id}, expires_at={self.expires_at})>"


class SleepRecord(Base):
    """Sleep data records from Whoop API."""

    __tablename__ = "sleep_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)
    timezone_offset = Column(String(10))

    # Sleep stages (in milliseconds, convert to minutes for display)
    light_sleep_duration = Column(Integer)  # milliseconds
    slow_wave_sleep_duration = Column(Integer)  # milliseconds
    rem_sleep_duration = Column(Integer)  # milliseconds
    awake_duration = Column(Integer)  # milliseconds

    # Metrics
    sleep_performance_percentage = Column(Numeric(5, 2))
    sleep_consistency_percentage = Column(Numeric(5, 2))
    respiratory_rate = Column(Numeric(5, 2))
    sleep_efficiency = Column(Numeric(5, 2))

    # Metadata
    score_state = Column(String(50), index=True)  # SCORED, PENDING_SCORE, UNSCORABLE
    is_nap = Column(Boolean, default=False)

    # Raw data for future-proofing
    raw_data = Column(JSONType)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="sleep_records")

    def __repr__(self) -> str:
        return (
            f"<SleepRecord(id={self.id}, user_id={self.user_id}, "
            f"start_time={self.start_time})>"
        )


class RecoveryRecord(Base):
    """Recovery data records from Whoop API."""

    __tablename__ = "recovery_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cycle_id = Column(UUID(as_uuid=True), index=True)  # Links to cycle if available

    # Timestamps
    created_at_whoop = Column(DateTime(timezone=True), nullable=False, index=True)

    # Recovery metrics
    recovery_score = Column(Numeric(5, 2))
    resting_heart_rate = Column(Integer)
    hrv_rmssd = Column(Numeric(7, 2))  # Heart Rate Variability in ms
    spo2_percentage = Column(Numeric(5, 2))  # Blood oxygen saturation
    skin_temp_celsius = Column(Numeric(5, 2))

    # Metadata
    score_state = Column(String(50))  # SCORED, PENDING_SCORE, UNSCORABLE
    calibrating = Column(Boolean, default=False)

    # Raw data
    raw_data = Column(JSONType)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="recovery_records")

    def __repr__(self) -> str:
        return (
            f"<RecoveryRecord(id={self.id}, user_id={self.user_id}, "
            f"recovery_score={self.recovery_score})>"
        )


class WorkoutRecord(Base):
    """Workout data records from Whoop API."""

    __tablename__ = "workout_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False)
    timezone_offset = Column(String(10))

    # Workout details
    sport_id = Column(Integer, index=True)
    sport_name = Column(String(100))

    # Strain and effort
    strain_score = Column(Numeric(5, 2))
    average_heart_rate = Column(Integer)
    max_heart_rate = Column(Integer)
    kilojoules = Column(Numeric(10, 2))

    # Distance and altitude
    distance_meters = Column(Numeric(10, 2))
    altitude_gain_meters = Column(Numeric(10, 2))
    altitude_change_meters = Column(Numeric(10, 2))

    # Heart rate zones (in milliseconds)
    zone_zero_duration = Column(Integer)
    zone_one_duration = Column(Integer)
    zone_two_duration = Column(Integer)
    zone_three_duration = Column(Integer)
    zone_four_duration = Column(Integer)
    zone_five_duration = Column(Integer)

    # Metadata
    score_state = Column(String(50), index=True)  # SCORED, PENDING_SCORE, UNSCORABLE

    # Raw data
    raw_data = Column(JSONType)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="workout_records")

    def __repr__(self) -> str:
        return (
            f"<WorkoutRecord(id={self.id}, user_id={self.user_id}, "
            f"sport_name='{self.sport_name}', strain={self.strain_score})>"
        )


class CycleRecord(Base):
    """Physiological cycle data records from Whoop API."""

    __tablename__ = "cycle_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False)
    timezone_offset = Column(String(10))

    # Cycle metrics
    strain_score = Column(Numeric(5, 2))
    kilojoules = Column(Numeric(10, 2))
    average_heart_rate = Column(Integer)
    max_heart_rate = Column(Integer)

    # Metadata
    score_state = Column(String(50), index=True)  # SCORED, PENDING_SCORE, UNSCORABLE

    # Raw data
    raw_data = Column(JSONType)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="cycle_records")

    def __repr__(self) -> str:
        return (
            f"<CycleRecord(id={self.id}, user_id={self.user_id}, "
            f"strain={self.strain_score})>"
        )


class SyncStatus(Base):
    """Track sync status for each data type per user."""

    __tablename__ = "sync_status"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    data_type = Column(
        String(50), nullable=False, index=True
    )  # 'sleep', 'recovery', 'workout', 'cycle'
    last_sync_time = Column(DateTime(timezone=True))
    last_record_time = Column(DateTime(timezone=True))  # Most recent record fetched
    status = Column(String(50))  # 'success', 'error', 'in_progress'
    error_message = Column(Text)
    records_fetched = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="sync_statuses")

    def __repr__(self) -> str:
        return (
            f"<SyncStatus(user_id={self.user_id}, data_type='{self.data_type}', "
            f"status='{self.status}')>"
        )

    __table_args__ = (
        # Unique constraint: one sync status per user per data type
        {"schema": None},
    )
