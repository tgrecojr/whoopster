"""Pydantic models for Whoop API responses."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Base Models and Mixins
# ============================================================================


class WhoopTimestampMixin(BaseModel):
    """Mixin for common timestamp fields in Whoop API responses."""

    start: datetime
    end: datetime
    timezone_offset: str


class WhoopScoreMixin(BaseModel):
    """Mixin for score state field."""

    score_state: str = Field(
        ..., description="SCORED, PENDING_SCORE, or UNSCORABLE"
    )


# ============================================================================
# Sleep Models
# ============================================================================


class SleepStages(BaseModel):
    """Sleep stages duration data."""

    light_sleep_duration_milli: int
    slow_wave_sleep_duration_milli: int
    rem_sleep_duration_milli: int
    awake_duration_milli: int

    class Config:
        from_attributes = True


class SleepScore(BaseModel):
    """Sleep score metrics."""

    sleep_performance_percentage: Optional[Decimal] = None
    sleep_consistency_percentage: Optional[Decimal] = None
    sleep_efficiency_percentage: Optional[Decimal] = None

    class Config:
        from_attributes = True


class SleepResponse(WhoopTimestampMixin, WhoopScoreMixin):
    """Sleep record from Whoop API."""

    id: UUID
    user_id: int
    nap: bool
    sleep_stages: Optional[SleepStages] = None
    score: Optional[SleepScore] = None
    respiratory_rate: Optional[Decimal] = None

    class Config:
        from_attributes = True


class SleepCollection(BaseModel):
    """Paginated collection of sleep records."""

    records: List[SleepResponse]
    next_token: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Recovery Models
# ============================================================================


class RecoveryScore(BaseModel):
    """Recovery score metrics."""

    recovery_score: Decimal
    resting_heart_rate: int
    hrv_rmssd_milli: Decimal  # Heart Rate Variability in milliseconds
    spo2_percentage: Optional[Decimal] = None
    skin_temp_celsius: Optional[Decimal] = None

    class Config:
        from_attributes = True


class RecoveryResponse(WhoopScoreMixin):
    """Recovery record from Whoop API."""

    id: UUID
    user_id: int
    cycle_id: UUID
    created_at: datetime
    score: Optional[RecoveryScore] = None
    calibrating: bool = False

    class Config:
        from_attributes = True


class RecoveryCollection(BaseModel):
    """Paginated collection of recovery records."""

    records: List[RecoveryResponse]
    next_token: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Workout Models
# ============================================================================


class WorkoutZoneDuration(BaseModel):
    """Heart rate zone durations for workouts."""

    zone_zero_milli: int
    zone_one_milli: int
    zone_two_milli: int
    zone_three_milli: int
    zone_four_milli: int
    zone_five_milli: int

    class Config:
        from_attributes = True


class WorkoutScore(BaseModel):
    """Workout score metrics."""

    strain: Decimal
    average_heart_rate: int
    max_heart_rate: int
    kilojoule: Decimal
    percent_recorded: Optional[Decimal] = None
    distance_meter: Optional[Decimal] = None
    altitude_gain_meter: Optional[Decimal] = None
    altitude_change_meter: Optional[Decimal] = None
    zone_duration: Optional[WorkoutZoneDuration] = None

    class Config:
        from_attributes = True


class WorkoutResponse(WhoopTimestampMixin, WhoopScoreMixin):
    """Workout record from Whoop API."""

    id: UUID
    user_id: int
    sport_id: int
    score: Optional[WorkoutScore] = None

    class Config:
        from_attributes = True


class WorkoutCollection(BaseModel):
    """Paginated collection of workout records."""

    records: List[WorkoutResponse]
    next_token: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Cycle Models
# ============================================================================


class CycleScore(BaseModel):
    """Cycle score metrics."""

    strain: Decimal
    kilojoule: Decimal
    average_heart_rate: int
    max_heart_rate: int

    class Config:
        from_attributes = True


class CycleResponse(WhoopTimestampMixin, WhoopScoreMixin):
    """Cycle record from Whoop API."""

    id: UUID
    user_id: int
    score: Optional[CycleScore] = None

    class Config:
        from_attributes = True


class CycleCollection(BaseModel):
    """Paginated collection of cycle records."""

    records: List[CycleResponse]
    next_token: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# OAuth Models
# ============================================================================


class OAuthToken(BaseModel):
    """OAuth token response from Whoop API."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds
    scope: str

    class Config:
        from_attributes = True


# ============================================================================
# Pagination Models
# ============================================================================


class PaginationParams(BaseModel):
    """Parameters for paginated API requests."""

    limit: int = Field(default=25, le=25, description="Max 25 per page")
    start: Optional[datetime] = Field(
        None, description="Filter records after this time"
    )
    end: Optional[datetime] = Field(
        None, description="Filter records before this time"
    )
    next_token: Optional[str] = Field(
        None, description="Token for next page of results"
    )

    class Config:
        from_attributes = True


# ============================================================================
# Sport ID Mapping (for reference)
# ============================================================================

SPORT_ID_MAP = {
    0: "Running",
    1: "Cycling",
    16: "Baseball",
    17: "Basketball",
    18: "Rowing",
    19: "Fencing",
    20: "Field Hockey",
    21: "Football",
    22: "Golf",
    24: "Ice Hockey",
    25: "Lacrosse",
    27: "Rugby",
    28: "Sailing",
    29: "Skiing",
    30: "Soccer",
    31: "Softball",
    32: "Squash",
    33: "Swimming",
    34: "Tennis",
    35: "Track & Field",
    36: "Volleyball",
    37: "Water Polo",
    38: "Wrestling",
    39: "Boxing",
    42: "Dance",
    43: "Pilates",
    44: "Yoga",
    45: "Weightlifting",
    47: "Cross Country Skiing",
    48: "Functional Fitness",
    49: "Duathlon",
    51: "Gymnastics",
    52: "Hiking/Rucking",
    53: "Horseback Riding",
    55: "Kayaking",
    56: "Martial Arts",
    57: "Mountain Biking",
    59: "Powerlifting",
    60: "Rock Climbing",
    61: "Paddleboarding",
    62: "Triathlon",
    63: "Walking",
    64: "Surfing",
    65: "Elliptical",
    66: "Stairmaster",
    70: "Meditation",
    71: "Other",
    73: "Diving",
    74: "Operations - Tactical",
    75: "Operations - Medical",
    76: "Operations - Flying",
    77: "Operations - Water",
    82: "Ultimate",
    83: "Climber",
    84: "Jumping Rope",
    85: "Australian Football",
    86: "Skateboarding",
    87: "Coaching",
    88: "Ice Bath",
    89: "Commuting",
    90: "Driving",
    91: "Obstacle Course",
    92: "Motor Racing",
    93: "HIIT",
    94: "Spin",
    95: "Jiu Jitsu",
    96: "Manual Labor",
    97: "Cricket",
    98: "Pickleball",
    99: "Inline Skating",
    100: "Box Fitness",
    101: "Spikeball",
    102: "Wheelchair Pushing",
    103: "Paddle Tennis",
    104: "Barre",
    105: "Stage Performance",
    106: "High Stress Work",
    107: "Parkour",
    108: "Gaelic Football",
    109: "Hurling/Camogie",
    110: "Circus Arts",
    121: "Massage Therapy",
    125: "Watching Sports",
    126: "Assault Bike",
    127: "Kickboxing",
    128: "Stretching",
    230: "Table Tennis",
    231: "Badminton",
    232: "Netball",
    233: "Sauna",
    234: "Disc Golf",
    235: "Yard Work",
    236: "Air Compression",
    237: "Percussive Massage",
    238: "Paintball",
    239: "Ice Skating",
    240: "Handball",
}
