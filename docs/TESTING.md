# Whoopster Testing Guide

## Overview

Whoopster has a comprehensive test suite with 133 tests covering unit tests, integration tests, and database tests. The test suite is designed for cross-database compatibility, running with SQLite in tests while supporting PostgreSQL in production.

## Test Suite Statistics

- **Total Tests**: 133 (132 passing, 1 skipped)
- **Pass Rate**: 99.2%
- **Code Coverage**: 67%
- **Test Types**:
  - Unit Tests: 95
  - Integration Tests: 37
  - Database Tests: 1

## Test Organization

### Directory Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures
├── unit/
│   ├── __init__.py
│   ├── test_config.py             # Configuration tests (5 tests)
│   ├── test_models.py             # Database model tests (9 tests)
│   ├── test_oauth.py              # OAuth client tests (9 tests)
│   ├── test_rate_limiter.py       # Rate limiting tests (6 tests)
│   ├── test_scheduler.py          # Job scheduler tests (17 tests)
│   ├── test_services.py           # Service layer tests (45 tests)
│   └── test_token_manager.py      # Token management tests (8 tests)
└── integration/
    ├── __init__.py
    ├── test_api_client.py         # API client tests (11 tests)
    ├── test_data_sync.py          # End-to-end sync tests (7 tests)
    └── test_database.py           # Database operations test (1 test)
```

### Test Markers

Tests are organized using pytest markers:

```python
@pytest.mark.unit           # Fast, isolated unit tests
@pytest.mark.integration    # Slower, multi-component tests
@pytest.mark.asyncio        # Async/await tests
@pytest.mark.slow           # Tests that take >1 second
```

**Run specific test types:**
```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run all except slow tests
pytest -m "not slow"

# Run async tests
pytest -m asyncio
```

## Running Tests

### Quick Start

```bash
# Run all tests
python -m pytest tests/

# Run with verbose output
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
python -m pytest tests/unit/test_services.py

# Run specific test
python -m pytest tests/unit/test_services.py::TestSleepService::test_sync_sleep_records
```

### Advanced Options

```bash
# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Increase verbosity
pytest -vv

# Run only failed tests from last run
pytest --lf

# Run tests matching pattern
pytest -k "test_sleep"

# Generate HTML coverage report
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

### Continuous Integration

```bash
# CI-friendly command (used in GitHub Actions)
pytest tests/ \
  --cov=src \
  --cov-report=term \
  --cov-report=xml \
  --junitxml=junit.xml \
  -v
```

## Test Fixtures

### Core Fixtures (tests/conftest.py)

#### Database Fixtures

**db_session**
```python
@pytest.fixture
def db_session():
    """Provide a transactional database session for testing.

    Creates an in-memory SQLite database, runs migrations,
    yields a session, then rolls back all changes.
    """
    # Create in-memory SQLite database
    engine = create_engine("sqlite:///:memory:")

    # Create all tables
    Base.metadata.create_all(engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Begin nested transaction
    session.begin_nested()

    yield session

    # Rollback to keep tests isolated
    session.rollback()
    session.close()
```

**Usage:**
```python
def test_create_user(db_session):
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()

    assert user.id is not None
```

#### Model Fixtures

**test_user**
```python
@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    user = User(
        whoop_user_id=12345,
        email="test@example.com",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
```

**test_oauth_token**
```python
@pytest.fixture
def test_oauth_token(db_session, test_user):
    """Create a test OAuth token."""
    token = OAuthToken(
        user_id=test_user.id,
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["read:sleep", "read:recovery"],
    )
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)
    return token
```

**test_sleep_record**, **test_recovery_record**, etc.
```python
@pytest.fixture
def test_sleep_record(db_session, test_user):
    """Create a test sleep record."""
    record = SleepRecord(
        id=uuid4(),
        user_id=test_user.id,
        start_time=datetime.now(timezone.utc) - timedelta(hours=8),
        end_time=datetime.now(timezone.utc),
        timezone_offset="-05:00",
        nap=False,
        score_state="SCORED",
        sleep_performance_percentage=85.5,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record
```

#### Mock Data Fixtures

**mock_whoop_sleep_response**
```python
@pytest.fixture
def mock_whoop_sleep_response():
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
                    "sleep_consistency_percentage": 80.0,
                    "sleep_efficiency_percentage": 95.0,
                },
            }
        ],
        "next_token": None,
    }
```

Similar fixtures exist for:
- `mock_whoop_recovery_response`
- `mock_whoop_workout_response`
- `mock_whoop_cycle_response`

## Test Patterns

### 1. Cross-Database Compatibility

Tests run with SQLite but production uses PostgreSQL. Handle differences:

**Timezone-Aware Datetimes:**
```python
def test_token_expiration(test_oauth_token, db_session):
    """Test that tokens can detect expiration."""
    now = datetime.now(timezone.utc)

    # SQLite may strip timezone info
    token_expiry = test_oauth_token.expires_at
    if token_expiry.tzinfo is None:
        token_expiry = token_expiry.replace(tzinfo=timezone.utc)

    time_until_expiry = token_expiry - now
    assert time_until_expiry.total_seconds() > 0
```

**Array/JSON Fields:**
```python
# TypeDecorators handle this automatically
# No special test code needed
scopes = ["read:sleep", "read:recovery"]
token.scopes = scopes  # Works in both PostgreSQL and SQLite
assert token.scopes == scopes
```

### 2. Mock Context Managers

Services use context managers for database sessions. Mock them properly:

```python
async def test_sync_sleep_records(test_user, db_session, mock_whoop_sleep_response):
    """Test syncing sleep records."""
    client = WhoopClient(user_id=test_user.id)
    service = SleepService(user_id=test_user.id, whoop_client=client)

    # Mock API client
    with patch.object(
        client,
        "get_sleep_records",
        new=AsyncMock(return_value=mock_whoop_sleep_response["records"]),
    ):
        # Mock database context - IMPORTANT: Must commit on __exit__
        def mock_exit(*args):
            db_session.commit()
            return None

        with patch("src.services.sleep_service.get_db_context") as mock_context:
            mock_context.return_value.__enter__.return_value = db_session
            mock_context.return_value.__exit__ = mock_exit

            records_synced = await service.sync_sleep_records()

            assert records_synced == 1
```

**Key Points:**
- `__enter__` returns the session
- `__exit__` commits the session (critical for assertions)
- Without commit, assertions won't see changes

### 3. Async Testing

Use pytest-asyncio for async tests:

```python
@pytest.mark.asyncio
async def test_async_operation():
    """Test async function."""
    result = await some_async_function()
    assert result is not None
```

**AsyncMock for async functions:**
```python
with patch.object(
    client,
    "async_method",
    new=AsyncMock(return_value="test_value"),
):
    result = await client.async_method()
    assert result == "test_value"
```

### 4. Async Event Loop Management

When testing code that runs async in sync context:

```python
def test_sync_wrapper_for_async():
    """Test synchronous wrapper around async code."""
    # Code uses ThreadPoolExecutor pattern
    result = sync_wrapper_function()  # Internally uses asyncio.run()
    assert result is not None
```

**Pattern in production code:**
```python
try:
    loop = asyncio.get_running_loop()
    # Loop already running, use thread pool
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, async_function())
        result = future.result()
except RuntimeError:
    # No loop running, safe to use run_until_complete
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(async_function())
```

### 5. Respx for HTTP Mocking

Integration tests use respx to mock HTTP calls:

```python
@respx.mock
async def test_api_call(test_user, test_oauth_token):
    """Test API client makes correct requests."""
    client = WhoopClient(user_id=test_user.id)

    # Mock token retrieval
    with patch.object(
        client.token_manager,
        "get_valid_token",
        new=AsyncMock(return_value=test_oauth_token.access_token),
    ):
        # Mock API endpoint
        respx.get(f"{client.base_url}/developer/v1/activity/sleep").mock(
            return_value=httpx.Response(200, json={"records": []})
        )

        # Make request
        records = await client.get_sleep_records()

        # Verify
        assert len(records) == 0
```

**Verify request details:**
```python
route = respx.get(f"{client.base_url}/developer/v1/activity/sleep")
route.mock(return_value=httpx.Response(200, json=data))

await client.get_sleep_records(start_time=some_time)

# Check request was made correctly
request = route.calls.last.request
assert "start" in str(request.url)
assert request.headers["Authorization"] == f"Bearer {token}"
```

### 6. Rate Limiter Testing

Test rate limiting behavior:

```python
@pytest.mark.asyncio
@pytest.mark.slow
async def test_rate_limiter_enforces_limit():
    """Test that rate limiter actually limits requests."""
    limiter = RateLimiter(max_requests=5, time_window=30)

    start_time = time.time()

    # Make 7 requests (5 + 2 over limit)
    for i in range(7):
        async with limiter.acquire():
            pass  # Simulate request

    end_time = time.time()
    duration = end_time - start_time

    # Should take at least 30 seconds (had to wait for window to reset)
    assert duration >= 30

    # Deque should have cleaned up old requests
    assert len(limiter.request_times) <= limiter.max_requests
```

### 7. Scheduler Testing

Use in-memory job store for scheduler tests:

```python
def test_start_scheduler():
    """Test starting the scheduler."""
    scheduler = WhoopScheduler(use_persistent_jobstore=False)

    scheduler.start()

    assert scheduler.scheduler.running is True

    # Cleanup
    scheduler.shutdown(wait=False)
```

**Key Points:**
- `use_persistent_jobstore=False` avoids PostgreSQL dependency
- Always clean up scheduler in tests
- Some shutdown behaviors differ in test vs production

### 8. Configuration Testing

Isolate configuration tests from .env files:

```python
def test_settings_has_defaults(monkeypatch, tmp_path):
    """Test that settings have default values."""
    # Clear environment variables
    monkeypatch.delenv("POSTGRES_DB", raising=False)

    # Set required variables
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")

    # Change to temp directory (no .env file)
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.postgres_db == "whoopster"
```

### 9. Testing UPSERT Behavior

Verify that re-syncing updates existing records:

```python
@respx.mock
async def test_upsert_behavior(db_session, test_user, test_oauth_token):
    """Test that sync performs upsert (updates existing records)."""
    client = WhoopClient(user_id=test_user.id)
    service = SleepService(user_id=test_user.id, whoop_client=client)

    # First sync with score = 80.0
    mock_data = {"records": [{"id": "same-uuid", "score": {"sleep_performance_percentage": 80.0}}]}

    route = respx.get(f"{client.base_url}/developer/v1/activity/sleep")
    route.mock(return_value=httpx.Response(200, json=mock_data))

    await service.sync_sleep_records()

    # Update score to 90.0
    mock_data["records"][0]["score"]["sleep_performance_percentage"] = 90.0
    route.mock(return_value=httpx.Response(200, json=mock_data))

    # Second sync
    await service.sync_sleep_records()

    # Refresh session to get latest data
    db_session.expire_all()

    # Should still have only 1 record
    records = db_session.query(SleepRecord).filter_by(user_id=test_user.id).all()
    assert len(records) == 1

    # But with updated value
    assert records[0].sleep_performance_percentage == 90.0
```

### 10. Testing Pagination

Test handling of multi-page API responses:

```python
@respx.mock
async def test_pagination(test_user, test_oauth_token):
    """Test pagination handling."""
    client = WhoopClient(user_id=test_user.id)

    # Page 1
    page1 = {
        "records": [{"id": "record-1"}],
        "next_token": "page2_token",
    }

    # Page 2
    page2 = {
        "records": [{"id": "record-2"}],
        "next_token": None,
    }

    route = respx.get(f"{client.base_url}/developer/v1/activity/sleep")
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]

    # Fetch all pages
    records = await client.get_sleep_records()

    # Should have combined both pages
    assert len(records) == 2
    assert records[0]["id"] == "record-1"
    assert records[1]["id"] == "record-2"
```

## Writing New Tests

### Unit Test Template

```python
@pytest.mark.unit
class TestMyComponent:
    """Tests for MyComponent."""

    def test_basic_functionality(self):
        """Test basic functionality."""
        component = MyComponent()
        result = component.do_something()
        assert result is not None

    def test_error_handling(self):
        """Test error handling."""
        component = MyComponent()

        with pytest.raises(ValueError, match="Invalid input"):
            component.do_something(invalid_input)

    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Test async operation."""
        component = MyComponent()
        result = await component.async_operation()
        assert result == expected_value
```

### Integration Test Template

```python
@pytest.mark.integration
@pytest.mark.asyncio
class TestEndToEndFlow:
    """Integration tests for complete flow."""

    @respx.mock
    async def test_complete_sync_flow(
        self,
        db_session,
        test_user,
        test_oauth_token,
        mock_whoop_sleep_response,
    ):
        """Test complete sync from API to database."""
        # Setup
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        # Mock dependencies
        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=test_oauth_token.access_token),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                respx.get(f"{client.base_url}/developer/v1/activity/sleep").mock(
                    return_value=httpx.Response(200, json=mock_whoop_sleep_response)
                )

                # Mock database context
                def mock_exit(*args):
                    db_session.commit()
                    return None

                with patch("src.services.sleep_service.get_db_context") as mock_context:
                    mock_context.return_value.__enter__.return_value = db_session
                    mock_context.return_value.__exit__ = mock_exit

                    # Execute
                    records_synced = await service.sync_sleep_records()

                    # Verify
                    assert records_synced == 1

                    sleep_records = db_session.query(SleepRecord).filter_by(
                        user_id=test_user.id
                    ).all()
                    assert len(sleep_records) == 1
                    assert sleep_records[0].sleep_performance_percentage == 85.5
```

### Best Practices

1. **Test One Thing**: Each test should verify one specific behavior
2. **Use Descriptive Names**: Test name should describe what's being tested
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Mock External Dependencies**: Don't call real APIs or databases
5. **Test Edge Cases**: Include error cases, empty data, boundary values
6. **Keep Tests Fast**: Unit tests should run in milliseconds
7. **Make Tests Independent**: Tests should not depend on execution order
8. **Use Fixtures**: Reuse common setup code via fixtures
9. **Clean Up Resources**: Close connections, shutdown schedulers
10. **Document Complex Tests**: Add comments explaining non-obvious logic

## Debugging Tests

### Run Single Test with Full Output

```bash
pytest tests/unit/test_services.py::TestSleepService::test_sync_sleep_records -vv -s
```

### Use pdb for Debugging

```python
def test_something():
    import pdb; pdb.set_trace()
    # Test code here
```

Or use pytest's built-in debugger:
```bash
pytest --pdb  # Drop into debugger on failure
pytest --trace  # Drop into debugger at start of each test
```

### Print Statements

```python
def test_something():
    result = do_something()
    print(f"Result: {result}")  # Will show with -s flag
    assert result is not None
```

Run with `-s` to see print output:
```bash
pytest tests/unit/test_something.py -s
```

### Logging in Tests

```python
import logging

def test_with_logging(caplog):
    """Test that captures log output."""
    with caplog.at_level(logging.INFO):
        do_something_that_logs()

    assert "Expected log message" in caplog.text
```

### Failed Test Output

Pytest shows detailed failure information:
```
FAILED tests/unit/test_services.py::TestSleepService::test_sync_sleep_records

_________________________ TestSleepService.test_sync_sleep_records __________________________

    async def test_sync_sleep_records(self, test_user, db_session):
        ...
        assert records_synced == 1
>       assert sync_status.status == "success"
E       AssertionError: assert 'error' == 'success'
E         - success
E         + error

tests/unit/test_services.py:76: AssertionError
```

## Coverage Analysis

### Generate Coverage Report

```bash
# Terminal report
pytest --cov=src --cov-report=term-missing

# HTML report (browsable)
pytest --cov=src --cov-report=html
open htmlcov/index.html

# XML report (for CI)
pytest --cov=src --cov-report=xml
```

### Coverage Report Example

```
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
src/__init__.py                             0      0   100%
src/api/__init__.py                         0      0   100%
src/api/rate_limiter.py                    42      5    88%   67-71
src/api/whoop_client.py                   128     42    67%   145-167, 201-223
src/auth/__init__.py                        0      0   100%
src/auth/oauth_client.py                   89     28    69%   98-112, 145-159
src/auth/token_manager.py                  87     15    83%   134-148
src/config.py                              31      0   100%
src/database/__init__.py                    0      0   100%
src/database/session.py                    23      5    78%   34-38
src/models/__init__.py                      0      0   100%
src/models/db_models.py                   187     31    83%   Various lines
src/scheduler/__init__.py                   0      0   100%
src/scheduler/job_scheduler.py             94     31    67%   Various lines
src/services/data_collector.py            103     35    66%   Various lines
src/services/sleep_service.py              68     12    82%   Various lines
---------------------------------------------------------------------
TOTAL                                     852    204    67%
```

### Improving Coverage

Focus on critical paths:
1. Error handling branches
2. Edge cases in business logic
3. Utility functions
4. Configuration loading

Don't obsess over 100%:
- Some code is hard to test (system interactions)
- Defensive code (shouldn't happen) may not be testable
- Focus on meaningful tests, not coverage percentage

## Common Test Failures

### 1. Database Connection Issues

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) unable to open database file
```

**Solution**: Ensure test uses in-memory database:
```python
engine = create_engine("sqlite:///:memory:")
```

### 2. Async Event Loop Already Running

```
RuntimeError: This event loop is already running
```

**Solution**: Use ThreadPoolExecutor pattern or pytest-asyncio properly:
```python
@pytest.mark.asyncio
async def test_async_function():
    # Test async code here
```

### 3. Timezone Comparison Errors

```
TypeError: can't compare offset-naive and offset-aware datetimes
```

**Solution**: Normalize timezones before comparison:
```python
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
```

### 4. Mock Context Manager Not Committing

```
AssertionError: assert None is not None
```

**Solution**: Add commit to mock exit:
```python
def mock_exit(*args):
    db_session.commit()
    return None

mock_context.return_value.__exit__ = mock_exit
```

### 5. Import Errors

```
ModuleNotFoundError: No module named 'src'
```

**Solution**: Run tests from project root:
```bash
cd /path/to/whoopster
python -m pytest tests/
```

### 6. Fixture Not Found

```
fixture 'test_user' not found
```

**Solution**: Ensure conftest.py is in correct location and fixture is defined:
```python
# tests/conftest.py
@pytest.fixture
def test_user(db_session):
    # ...
```

## Performance Testing

### Benchmark Tests

Use pytest-benchmark for performance tests:

```python
def test_database_query_performance(benchmark, db_session, test_user):
    """Benchmark database query performance."""
    # Create test data
    for i in range(1000):
        db_session.add(SleepRecord(...))
    db_session.commit()

    # Benchmark query
    result = benchmark(
        lambda: db_session.query(SleepRecord).filter_by(user_id=test_user.id).all()
    )

    assert len(result) == 1000
```

### Load Testing

For integration tests, simulate multiple concurrent requests:

```python
@pytest.mark.slow
async def test_concurrent_syncs():
    """Test handling concurrent sync requests."""
    tasks = [sync_user_data(user_id=i) for i in range(10)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Verify all succeeded
    for result in results:
        assert not isinstance(result, Exception)
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov pytest-asyncio

    - name: Run tests
      run: |
        pytest tests/ \
          --cov=src \
          --cov-report=term \
          --cov-report=xml \
          --junitxml=junit.xml \
          -v

    - name: Upload coverage
      uses: codecov/codecov-action@v2
      with:
        files: ./coverage.xml
        fail_ci_if_error: true
```

### Pre-commit Hooks

```bash
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest tests/ -v
        language: system
        pass_filenames: false
        always_run: true
```

## Test Data Management

### Realistic Test Data

Use realistic data that matches production:

```python
@pytest.fixture
def realistic_sleep_record():
    """Create realistic sleep record."""
    return {
        "id": str(uuid4()),
        "start": "2025-12-18T22:30:00.000Z",  # Realistic bedtime
        "end": "2025-12-19T07:15:00.000Z",    # Realistic wake time
        "timezone_offset": "-05:00",
        "nap": False,
        "score_state": "SCORED",
        "score": {
            "stage_summary": {
                "total_light_sleep_time_milli": 14400000,  # 4 hours
                "total_slow_wave_sleep_time_milli": 7200000,  # 2 hours
                "total_rem_sleep_time_milli": 5400000,  # 1.5 hours
                "total_awake_time_milli": 1800000,  # 30 minutes
            },
            "sleep_performance_percentage": 87.0,
            "sleep_consistency_percentage": 82.0,
            "sleep_efficiency_percentage": 94.0,
        },
    }
```

### Test Data Factories

For complex data, consider factory pattern:

```python
class SleepRecordFactory:
    @staticmethod
    def create(
        user_id: int,
        sleep_hours: float = 8.0,
        performance: float = 85.0,
        **kwargs
    ) -> SleepRecord:
        """Create sleep record with sensible defaults."""
        end_time = kwargs.get("end_time", datetime.now(timezone.utc))
        start_time = kwargs.get("start_time", end_time - timedelta(hours=sleep_hours))

        return SleepRecord(
            id=kwargs.get("id", uuid4()),
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            sleep_performance_percentage=performance,
            **kwargs
        )

# Usage
record = SleepRecordFactory.create(user_id=1, sleep_hours=7.5, performance=90.0)
```

## Skipping Tests

### Temporarily Skip a Test

```python
@pytest.mark.skip(reason="Temporarily disabled while fixing bug #123")
def test_broken_feature():
    pass
```

### Conditional Skip

```python
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Unix-only test"
)
def test_unix_feature():
    pass
```

### Expected Failure

```python
@pytest.mark.xfail(reason="Known issue with SQLite UUID handling")
def test_known_issue():
    # Test that currently fails but we expect to fix
    pass
```

## Troubleshooting Test Environment

### Clear Test Database

```bash
# Tests use in-memory SQLite, nothing to clear
# But if you're using a test PostgreSQL database:
dropdb whoopster_test
createdb whoopster_test
```

### Reset Test Coverage

```bash
rm -rf .coverage htmlcov/ .pytest_cache/
```

### Reinstall Dependencies

```bash
pip install -r requirements.txt --force-reinstall
```

### Verify Test Environment

```python
# tests/test_environment.py
def test_environment():
    """Verify test environment is configured correctly."""
    import sys
    import sqlalchemy
    import pytest
    import httpx

    assert sys.version_info >= (3, 11)
    assert sqlalchemy.__version__.startswith("2.0")
    print(f"Python: {sys.version}")
    print(f"SQLAlchemy: {sqlalchemy.__version__}")
    print(f"pytest: {pytest.__version__}")
    print(f"httpx: {httpx.__version__}")
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [respx Documentation](https://lundberg.github.io/respx/)
- [SQLAlchemy Testing Documentation](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [Pydantic Testing](https://docs.pydantic.dev/latest/concepts/testing/)
