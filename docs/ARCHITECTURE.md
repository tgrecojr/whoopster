# Whoopster Architecture

## Overview

Whoopster is a Python-based data collection and visualization system that periodically synchronizes Whoop wearable data to a PostgreSQL database and displays it through Grafana dashboards.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                          │
│                                                                 │
│  ┌──────────────┐        ┌──────────────┐                      │
│  │   Grafana    │◄───────┤  PostgreSQL  │                      │
│  │  Dashboards  │        │  Datasource  │                      │
│  └──────────────┘        └──────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
                                 ▲
                                 │
                                 │ SQL Queries
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                       Data Storage Layer                        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              PostgreSQL Database                         │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐         │  │
│  │  │ Users  │  │ Tokens │  │ Sleep  │  │ Sync   │         │  │
│  │  │        │  │        │  │Records │  │Status  │  ...    │  │
│  │  └────────┘  └────────┘  └────────┘  └────────┘         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                 ▲
                                 │
                                 │ SQLAlchemy ORM
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                    Application Layer (Python)                   │
│                                                                 │
│  ┌──────────────┐       ┌──────────────────────────────────┐   │
│  │  APScheduler │──────►│      Data Collector              │   │
│  │  (15 min)    │       │  ┌────────────┐  ┌────────────┐  │   │
│  └──────────────┘       │  │   Sleep    │  │  Recovery  │  │   │
│                         │  │  Service   │  │  Service   │  │   │
│                         │  └────────────┘  └────────────┘  │   │
│                         │  ┌────────────┐  ┌────────────┐  │   │
│                         │  │  Workout   │  │   Cycle    │  │   │
│                         │  │  Service   │  │  Service   │  │   │
│                         │  └────────────┘  └────────────┘  │   │
│                         └──────────────────────────────────┘   │
│                                    │                           │
│                                    ▼                           │
│                         ┌──────────────────────────────────┐   │
│                         │       Whoop Client               │   │
│                         │  ┌────────────┐  ┌────────────┐  │   │
│                         │  │   Token    │  │    Rate    │  │   │
│                         │  │  Manager   │  │  Limiter   │  │   │
│                         │  └────────────┘  └────────────┘  │   │
│                         └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 │ HTTPS + OAuth 2.0
                                 ▼
                    ┌────────────────────────────┐
                    │    Whoop API (v2)          │
                    │  /v2/activity/sleep        │
                    │  /v2/activity/workout      │
                    │  /v2/recovery              │
                    │  /v2/cycle                 │
                    └────────────────────────────┘
```

## Database Schema

### Entity Relationship Diagram

```
┌──────────────────┐
│      User        │
│──────────────────│
│ id (PK)          │
│ whoop_user_id    │◄──────────┐
│ email            │           │
│ created_at       │           │ 1:N
│ updated_at       │           │
└──────────────────┘           │
                               │
                    ┌──────────┴──────────┐
                    │                     │
         ┌──────────────────┐  ┌──────────────────┐
         │   OAuthToken     │  │   SyncStatus     │
         │──────────────────│  │──────────────────│
         │ id (PK)          │  │ id (PK)          │
         │ user_id (FK)     │  │ user_id (FK)     │
         │ access_token     │  │ data_type        │
         │ refresh_token    │  │ last_sync_time   │
         │ expires_at       │  │ last_record_time │
         │ scopes           │  │ status           │
         │ created_at       │  │ records_fetched  │
         │ updated_at       │  │ error_message    │
         └──────────────────┘  └──────────────────┘

         ┌──────────────────┐
         │   SleepRecord    │
         │──────────────────│
         │ id (UUID, PK)    │
         │ user_id (FK)     │
         │ start_time       │
         │ end_time         │
         │ timezone_offset  │
         │ nap              │
         │ score_state      │
         │ sleep_perf_%     │
         │ light_sleep_ms   │
         │ rem_sleep_ms     │
         │ sws_ms           │
         │ awake_time_ms    │
         │ raw_data (JSON)  │
         │ created_at       │
         └──────────────────┘
                │
                │ Similar structure for:
                │ - RecoveryRecord
                │ - WorkoutRecord
                │ - CycleRecord
                ▼
```

### Table Details

#### users
Primary table for storing user information.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key (auto-increment) |
| whoop_user_id | INTEGER | Whoop's internal user ID |
| email | VARCHAR(255) | User's email address |
| created_at | TIMESTAMP | Record creation time (UTC) |
| updated_at | TIMESTAMP | Last update time (UTC) |

**Indexes:**
- `idx_users_whoop_user_id` on `whoop_user_id`
- `idx_users_email` on `email`

**Relationships:**
- One-to-many with `oauth_tokens`
- One-to-many with `sync_status`
- One-to-many with all record tables

#### oauth_tokens
Stores OAuth 2.0 tokens for API authentication.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| user_id | INTEGER | Foreign key to users |
| access_token | TEXT | Current access token (encrypted in production) |
| refresh_token | TEXT | Refresh token for obtaining new access tokens |
| expires_at | TIMESTAMP | Token expiration time (UTC) |
| scopes | ARRAY[TEXT] | Granted OAuth scopes |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last update time |

**Indexes:**
- `idx_oauth_tokens_user_id` on `user_id`

**Security Notes:**
- Tokens should be encrypted at rest in production
- Access tokens expire after 1 hour
- Refresh tokens have longer validity

#### sleep_records
Stores sleep session data from Whoop.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Whoop's sleep ID (primary key) |
| user_id | INTEGER | Foreign key to users |
| start_time | TIMESTAMP | Sleep start time (UTC) |
| end_time | TIMESTAMP | Sleep end time (UTC) |
| timezone_offset | VARCHAR(10) | Original timezone (e.g., "-05:00") |
| nap | BOOLEAN | True if nap, false if main sleep |
| score_state | VARCHAR(50) | "SCORED" or "PENDING_SCORE" |
| sleep_performance_percentage | FLOAT | Sleep quality score (0-100) |
| sleep_consistency_percentage | FLOAT | Consistency score |
| sleep_efficiency_percentage | FLOAT | Time asleep / time in bed |
| light_sleep_duration | INTEGER | Light sleep time (milliseconds) |
| slow_wave_sleep_duration | INTEGER | Deep sleep time (milliseconds) |
| rem_sleep_duration | INTEGER | REM sleep time (milliseconds) |
| awake_time | INTEGER | Awake time during sleep (milliseconds) |
| sleep_cycle_count | INTEGER | Number of sleep cycles |
| disturbance_count | INTEGER | Number of disturbances |
| raw_data | JSONB | Complete API response |
| created_at | TIMESTAMP | Record creation time |

**Indexes:**
- `idx_sleep_user_id` on `user_id`
- `idx_sleep_start_time` on `start_time`
- `idx_sleep_score_state` on `score_state`

**Unique Constraint:**
- UUID primary key ensures no duplicates

#### recovery_records
Stores daily recovery data.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Whoop's recovery ID |
| user_id | INTEGER | Foreign key to users |
| cycle_id | UUID | Associated cycle ID |
| sleep_id | UUID | Associated sleep ID |
| created_at_whoop | TIMESTAMP | When Whoop created this record |
| updated_at_whoop | TIMESTAMP | When Whoop last updated |
| score_state | VARCHAR(50) | "SCORED" or "PENDING_SCORE" |
| recovery_score | FLOAT | Recovery score (0-100) |
| resting_heart_rate | FLOAT | Morning resting HR (bpm) |
| hrv_rmssd | FLOAT | Heart rate variability (ms) |
| spo2_percentage | FLOAT | Blood oxygen saturation |
| skin_temp_celsius | FLOAT | Skin temperature |
| raw_data | JSONB | Complete API response |
| created_at | TIMESTAMP | Record creation time |

**Indexes:**
- `idx_recovery_user_id` on `user_id`
- `idx_recovery_created_at` on `created_at_whoop`
- `idx_recovery_score_state` on `score_state`

#### workout_records
Stores workout/activity data.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Whoop's workout ID |
| user_id | INTEGER | Foreign key to users |
| start_time | TIMESTAMP | Workout start (UTC) |
| end_time | TIMESTAMP | Workout end (UTC) |
| timezone_offset | VARCHAR(10) | Original timezone |
| sport_id | INTEGER | Whoop's sport identifier |
| sport_name | VARCHAR(100) | Sport/activity name |
| score_state | VARCHAR(50) | Scoring status |
| strain_score | FLOAT | Cardiovascular strain (0-21) |
| average_heart_rate | INTEGER | Average HR (bpm) |
| max_heart_rate | INTEGER | Max HR (bpm) |
| kilojoules | FLOAT | Energy expenditure |
| distance_meters | FLOAT | Distance covered |
| altitude_gain_meters | FLOAT | Elevation gain |
| altitude_change_meters | FLOAT | Net elevation change |
| zone_zero_duration | INTEGER | HR zone 0 time (ms) |
| zone_one_duration | INTEGER | HR zone 1 time (ms) |
| zone_two_duration | INTEGER | HR zone 2 time (ms) |
| zone_three_duration | INTEGER | HR zone 3 time (ms) |
| zone_four_duration | INTEGER | HR zone 4 time (ms) |
| zone_five_duration | INTEGER | HR zone 5 time (ms) |
| raw_data | JSONB | Complete API response |
| created_at | TIMESTAMP | Record creation time |

**Indexes:**
- `idx_workout_user_id` on `user_id`
- `idx_workout_start_time` on `start_time`
- `idx_workout_sport_name` on `sport_name`

#### cycle_records
Stores physiological cycle data (24-hour periods).

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Whoop's cycle ID |
| user_id | INTEGER | Foreign key to users |
| start_time | TIMESTAMP | Cycle start (UTC) |
| end_time | TIMESTAMP | Cycle end (UTC) |
| timezone_offset | VARCHAR(10) | Original timezone |
| score_state | VARCHAR(50) | Scoring status |
| strain_score | FLOAT | Day strain (0-21) |
| kilojoules | FLOAT | Total energy expenditure |
| average_heart_rate | INTEGER | Average HR for day |
| max_heart_rate | INTEGER | Max HR for day |
| raw_data | JSONB | Complete API response |
| created_at | TIMESTAMP | Record creation time |

**Indexes:**
- `idx_cycle_user_id` on `user_id`
- `idx_cycle_start_time` on `start_time`

#### sync_status
Tracks synchronization status for each data type.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| user_id | INTEGER | Foreign key to users |
| data_type | VARCHAR(50) | "sleep", "recovery", "workout", or "cycle" |
| last_sync_time | TIMESTAMP | When last sync started |
| last_record_time | TIMESTAMP | Most recent record timestamp |
| status | VARCHAR(50) | "success", "error", or "in_progress" |
| records_fetched | INTEGER | Count of records in last sync |
| error_message | TEXT | Error details if status is "error" |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last update time |

**Indexes:**
- `idx_sync_status_user_data_type` on `(user_id, data_type)`

**Unique Constraint:**
- `(user_id, data_type)` - one status record per user per data type

## Component Details

### Authentication Layer

#### OAuth 2.0 Flow (src/auth/oauth_client.py)

The application uses OAuth 2.0 with PKCE (Proof Key for Code Exchange) for secure authentication:

1. **Authorization URL Generation**
   - Creates PKCE code verifier and challenge
   - Builds authorization URL with required scopes
   - User grants access via browser

2. **Token Exchange**
   - Exchanges authorization code for access/refresh tokens
   - Stores tokens securely in database
   - Validates token response

3. **Token Refresh**
   - Automatically refreshes tokens before expiration
   - Updates database with new tokens
   - Handles refresh failures gracefully

**Key Classes:**
- `OAuthClient` - Manages OAuth flow and token exchange
- `TokenManager` - Handles token storage and refresh logic

**Security Features:**
- PKCE for enhanced security
- Secure token storage (encrypted in production)
- Automatic token rotation
- Scope validation

### API Layer

#### Whoop Client (src/api/whoop_client.py)

Central client for all Whoop API interactions.

**Features:**
- Automatic pagination handling
- Token refresh integration
- Rate limiting enforcement
- Retry logic with exponential backoff
- Comprehensive error handling

**Methods:**
- `get_sleep_records(start, end, next_token)` - Fetch sleep data
- `get_recovery_records(start, end, next_token)` - Fetch recovery data
- `get_workout_records(start, end, next_token)` - Fetch workout data
- `get_cycle_records(start, end, next_token)` - Fetch cycle data

**Pagination:**
```python
async def _paginated_request(self, endpoint, params):
    """Fetch all pages from a paginated endpoint."""
    all_records = []
    next_token = None

    while True:
        if next_token:
            params["nextToken"] = next_token

        response_data = await self._make_request(endpoint, params)
        records = response_data.get("records", [])
        all_records.extend(records)

        next_token = response_data.get("next_token")
        if not next_token:
            break

    return all_records
```

#### Rate Limiter (src/api/rate_limiter.py)

Implements sliding window rate limiting to comply with Whoop's API limits (60 requests/minute).

**Algorithm:**
- Tracks timestamps of recent requests in deque
- Removes requests older than time window
- Sleeps if limit reached
- 0.9 safety margin (54 requests/min actual limit)

**Usage:**
```python
async with rate_limiter.acquire():
    response = await httpx_client.get(url)
```

### Service Layer

#### Data Collector (src/services/data_collector.py)

Orchestrates synchronization across all data types.

**Key Methods:**
- `sync_all_data(data_types=None)` - Sync specified or all types
- `sync_sleep()` - Sync sleep records only
- `sync_recovery()` - Sync recovery records only
- `sync_workout()` - Sync workout records only
- `sync_cycle()` - Sync cycle records only
- `get_all_statistics()` - Retrieve statistics for all types

**Error Handling:**
- Continues syncing other types if one fails
- Logs errors with full context
- Returns summary with success/failure counts

#### Service Pattern (sleep_service.py, recovery_service.py, etc.)

Each data type has a dedicated service class following a common pattern:

```python
class SleepService:
    def __init__(self, user_id: int, whoop_client: WhoopClient):
        self.user_id = user_id
        self.whoop_client = whoop_client

    async def sync_sleep_records(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Sync sleep records from API to database."""
        # 1. Determine time range (incremental vs full)
        # 2. Fetch records from API
        # 3. Transform API records to database format
        # 4. Upsert records to database
        # 5. Update sync status
        # 6. Return count of records synced

    def _transform_api_record(self, api_record: dict) -> dict:
        """Transform API response to database format."""
        # Extract and validate fields
        # Convert timestamps
        # Store raw JSON
        # Return database-ready dict

    async def get_sleep_statistics(self) -> dict:
        """Get statistics for sleep records."""
        # Query database for aggregates
        # Return summary statistics
```

**Common Operations:**
1. **Incremental Sync**: Query `sync_status` for last record time, use as `start` parameter
2. **Full Sync**: No time filter, fetch all historical data
3. **UPSERT**: Use `ON CONFLICT DO UPDATE` to handle duplicates
4. **Status Tracking**: Update `sync_status` after each sync

### Scheduler

#### APScheduler Integration (src/scheduler/job_scheduler.py)

Uses APScheduler with PostgreSQL job store for persistent scheduling.

**Configuration:**
```python
jobstores = {
    "default": SQLAlchemyJobStore(url=settings.database_url),
}
executors = {
    "default": AsyncIOExecutor(),
}
job_defaults = {
    "coalesce": True,  # Skip missed runs
    "max_instances": 1,  # Prevent overlapping runs
    "misfire_grace_time": 300,  # 5-minute tolerance
}
```

**Job Management:**
- `add_user_sync_job(user_id)` - Schedule periodic sync for user
- `remove_user_sync_job(user_id)` - Remove user's sync job
- `add_all_users()` - Add jobs for all users in database
- `run_user_sync_now(user_id)` - Trigger immediate sync
- `get_job_status(user_id)` - Get next run time and status

**Persistence:**
- Jobs stored in PostgreSQL survive application restarts
- Job state maintained across deployments
- Automatic recovery from crashes

### Data Models

#### Pydantic Models (src/models/api_models.py)

Validate and parse API responses.

**Examples:**
```python
class SleepScore(BaseModel):
    stage_summary: StageSummary
    sleep_performance_percentage: float
    sleep_consistency_percentage: Optional[float]
    sleep_efficiency_percentage: float

class SleepRecord(BaseModel):
    id: str
    start: datetime
    end: datetime
    timezone_offset: str
    nap: bool
    score_state: str
    score: Optional[SleepScore]
```

**Benefits:**
- Automatic validation
- Type safety
- Clear API contracts
- Self-documenting

#### SQLAlchemy Models (src/models/db_models.py)

Define database schema and relationships.

**Cross-Database Compatibility:**
```python
class StringArray(TypeDecorator):
    """Works with PostgreSQL ARRAY and SQLite JSON."""
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(ARRAY(Text))
        else:
            return dialect.type_descriptor(Text)

    # ... serialization logic ...
```

**Relationships:**
```python
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    oauth_tokens = relationship("OAuthToken", back_populates="user")
    sleep_records = relationship("SleepRecord", back_populates="user")
    # ... more relationships
```

## Data Flow

### Initial Sync Flow

```
1. APScheduler triggers sync job
           ↓
2. DataCollector.sync_all_data()
           ↓
3. For each data type (sleep, recovery, workout, cycle):
           ↓
4. Check sync_status for last_record_time
           ↓
5. If first sync: start_time = None (fetch all)
   If incremental: start_time = last_record_time
           ↓
6. WhoopClient.get_*_records(start_time)
           ↓
7. Token Manager validates/refreshes token
           ↓
8. Rate Limiter enforces API limits
           ↓
9. Make API request (with pagination)
           ↓
10. API returns records (potentially multiple pages)
           ↓
11. Service transforms API records to DB format
           ↓
12. Upsert records to PostgreSQL (ON CONFLICT DO UPDATE)
           ↓
13. Update sync_status with last_record_time, count, status
           ↓
14. Return sync results
           ↓
15. DataCollector aggregates all results
           ↓
16. Log sync summary
```

### Token Refresh Flow

```
1. API request needs token
           ↓
2. TokenManager.get_valid_token()
           ↓
3. Query oauth_tokens table for user
           ↓
4. Check token expiration
           ↓
5. If expires within 5 minutes:
           ↓
6. OAuthClient.refresh_access_token(refresh_token)
           ↓
7. POST to Whoop token endpoint
           ↓
8. Receive new access_token and refresh_token
           ↓
9. Update oauth_tokens table
           ↓
10. Return new access_token
           ↓
11. Use token in API request
```

### Visualization Flow

```
1. User opens Grafana dashboard
           ↓
2. Grafana loads pre-provisioned PostgreSQL datasource
           ↓
3. Dashboard panels execute SQL queries
           ↓
4. PostgreSQL returns time-series data
           ↓
5. Grafana renders charts/graphs
           ↓
6. User interacts with filters/time ranges
           ↓
7. Queries re-execute with new parameters
           ↓
8. Dashboard updates in real-time
```

## Design Decisions

### Why PostgreSQL?

1. **JSONB Support**: Efficient storage and querying of raw API responses
2. **Array Types**: Native support for scopes and other array fields
3. **Persistent Job Store**: APScheduler requires SQL database
4. **Time-Series Performance**: Optimized for timestamp-based queries
5. **UPSERT Operations**: Native `ON CONFLICT DO UPDATE` syntax
6. **Grafana Integration**: First-class PostgreSQL datasource support

### Why UUID Primary Keys?

1. **Natural Deduplication**: Whoop uses UUIDs, we use same IDs
2. **Idempotent Syncs**: Re-syncing same data won't create duplicates
3. **No ID Conflicts**: No collision risk across distributed systems
4. **API Alignment**: Direct mapping to Whoop's identifiers

### Why APScheduler?

1. **Async Support**: AsyncIOExecutor for async/await code
2. **Persistent Jobs**: PostgreSQL job store survives restarts
3. **Flexible Triggers**: Interval, cron, date-based scheduling
4. **Job Management**: Add/remove/modify jobs at runtime
5. **Misfire Handling**: Configurable behavior for missed runs

### Why Separate Services?

1. **Single Responsibility**: Each service handles one data type
2. **Testability**: Easy to mock and test in isolation
3. **Maintainability**: Clear code organization
4. **Flexibility**: Can sync individual types independently
5. **Error Isolation**: Failure in one doesn't affect others

### Why Store Raw JSON?

1. **Future-Proofing**: API changes won't break existing data
2. **Complete History**: Preserve all fields even if not used
3. **Debugging**: Original API response available for troubleshooting
4. **Data Recovery**: Can re-process if schema changes
5. **Audit Trail**: Complete record of what API returned

### Why Incremental Sync?

1. **Performance**: Only fetch new data after initial sync
2. **API Limits**: Reduces request count and data transfer
3. **Cost Efficiency**: Less bandwidth and processing
4. **Faster Updates**: Minutes to sync new data vs hours for full history
5. **Rate Limit Compliance**: Easier to stay within 60 req/min limit

## Deployment Architecture

### Docker Compose Services

```yaml
services:
  postgres:
    - PostgreSQL 15 database
    - Persistent volume: ./postgres_data:/var/lib/postgresql/data
    - Health checks before app starts
    - Port 5432 exposed for debugging

  app:
    - Python 3.11 application
    - Runs Alembic migrations on startup
    - Auto-restarts on failure
    - Depends on postgres health
    - Logs to persistent volume

  grafana:
    - Grafana 10.2 for visualization
    - Auto-provisions PostgreSQL datasource
    - Pre-loaded dashboards
    - Port 3000 for web access
    - Persistent volume for configs
```

### Environment-Specific Configuration

**Development:**
- SQLite for tests (in-memory)
- Debug logging enabled
- No SSL required
- Local file storage

**Production:**
- PostgreSQL with SSL
- Info/Warning logs only
- Encrypted token storage
- S3 for backups
- Multiple app replicas

## Performance Considerations

### Database Indexes

All frequently queried columns have indexes:
- `user_id` on all record tables
- Timestamps (`start_time`, `created_at`)
- Status fields (`score_state`, `status`)

**Query Optimization:**
```sql
-- Efficient: Uses idx_sleep_user_id and idx_sleep_start_time
SELECT * FROM sleep_records
WHERE user_id = 1
  AND start_time >= '2024-01-01'
ORDER BY start_time DESC;

-- Inefficient: Full table scan
SELECT * FROM sleep_records
WHERE sleep_performance_percentage > 85;
```

### Rate Limiting Strategy

- **API Limit**: 60 requests/minute
- **Our Limit**: 54 requests/minute (90% safety margin)
- **Algorithm**: Sliding window with deque
- **Graceful Degradation**: Sleeps instead of failing

### Pagination Handling

- Automatically fetches all pages
- Yields records as they arrive (streaming)
- Memory-efficient for large datasets
- Respects rate limits between pages

### Incremental Sync

After initial sync, subsequent runs are fast:
- **Initial Sync**: Hours (years of historical data)
- **Incremental Sync**: Seconds (last 15 minutes of data)
- Uses `last_record_time` from `sync_status`
- Only processes new/updated records

## Security Considerations

### Token Storage

**Development:**
- Plain text in PostgreSQL (acceptable for local dev)

**Production:**
- Encrypt tokens at rest using application-level encryption
- Use environment variables for encryption keys
- Rotate keys periodically
- Consider AWS Secrets Manager or HashiCorp Vault

### API Security

- OAuth 2.0 with PKCE for secure authentication
- HTTPS for all API communication
- Token refresh before expiration
- Secure redirect URI validation

### Database Security

- Use strong passwords (generated, not default)
- Restrict PostgreSQL network access
- Enable SSL for database connections in production
- Regular backups with encryption
- Principle of least privilege for database users

### Grafana Security

- Change default admin password
- Enable HTTPS in production
- Configure authentication (OAuth, LDAP, etc.)
- Restrict dashboard editing permissions
- Use read-only database user for Grafana

## Monitoring and Observability

### Logging

Structured JSON logging with context:
```python
logger.info(
    "Sync completed",
    user_id=user_id,
    data_type="sleep",
    records_synced=count,
    duration_seconds=duration,
)
```

**Log Levels:**
- DEBUG: Detailed request/response data
- INFO: Sync operations, job scheduling
- WARNING: Rate limit approaching, token expiring soon
- ERROR: API failures, database errors
- CRITICAL: Service crashes, data corruption

### Metrics to Monitor

**Application:**
- Sync success rate per data type
- Average sync duration
- API error rate
- Token refresh failures
- Rate limit violations

**Database:**
- Connection pool usage
- Query performance
- Table sizes
- Index usage
- Lock contention

**Infrastructure:**
- CPU/Memory usage
- Disk I/O
- Network throughput
- Container restarts

### Health Checks

**Database:**
```python
async def check_database_health():
    try:
        await db.execute("SELECT 1")
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

**API:**
```python
async def check_api_health():
    try:
        token = await token_manager.get_valid_token()
        return {"status": "healthy", "token_expires_in": token.expires_in}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

## Testing Strategy

See [TESTING.md](./TESTING.md) for comprehensive testing documentation.

**Test Pyramid:**
- Unit Tests (95 tests): Fast, isolated component tests
- Integration Tests (37 tests): End-to-end flow verification
- Coverage: 67% (focused on critical paths)

**Key Testing Patterns:**
- Cross-database compatibility (PostgreSQL/SQLite)
- Mock context managers with proper commit behavior
- Timezone-aware datetime handling
- Async event loop management
- Transaction-based test isolation

## Migration Strategy

See detailed migration workflow in main [implementation plan](../README.md#database-migrations-with-alembic).

**Key Points:**
- Alembic manages all schema changes
- Migrations auto-run on startup
- Version-controlled migration scripts
- Support for data migrations
- Downgrade paths for rollback

## Future Enhancements

### Multi-User Support

Schema already supports multiple users:
- Add user registration endpoint
- Implement per-user OAuth flow
- Isolate data by user_id
- User management UI

### Real-Time Updates

- Whoop webhook support for instant data
- WebSocket notifications to Grafana
- Reduce sync interval to 5 minutes
- Push notifications for low recovery

### Advanced Analytics

- Trend analysis (sleep trending up/down)
- Correlation analysis (recovery vs workout strain)
- Predictive modeling (injury risk, performance forecast)
- Machine learning for personalized insights

### Data Export

- CSV/JSON export functionality
- Apple Health integration
- Google Fit integration
- Third-party app connectors

### Web UI

- OAuth management interface
- Sync job configuration
- Data visualization (alternative to Grafana)
- User preferences and settings

## Troubleshooting

### Common Issues

**Issue: Migrations fail on startup**
```bash
# Check Alembic version
alembic current

# Verify database connection
python -c "from src.database.session import engine; engine.connect()"

# Manual migration
alembic upgrade head
```

**Issue: Token refresh fails**
```python
# Check token expiration
SELECT expires_at, created_at FROM oauth_tokens WHERE user_id = 1;

# Manually refresh
python scripts/init_oauth.py
```

**Issue: API rate limit exceeded**
```python
# Check recent requests
# Increase delay in rate limiter
# Reduce sync frequency
```

See main README for more troubleshooting scenarios.

## References

- [Whoop API Documentation](https://developer.whoop.com)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Grafana Documentation](https://grafana.com/docs/)
