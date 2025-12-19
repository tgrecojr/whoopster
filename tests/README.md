# Whoopster Test Suite

Comprehensive test suite for the Whoopster application using pytest.

## Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures and configuration
├── README.md                # This file
├── unit/                    # Unit tests
│   ├── test_config.py       # Configuration tests
│   ├── test_models.py       # Database model tests
│   ├── test_oauth_client.py # OAuth client tests
│   ├── test_token_manager.py# Token management tests
│   ├── test_rate_limiter.py # Rate limiter tests
│   ├── test_whoop_client.py # Whoop API client tests
│   ├── test_services.py     # Service layer tests
│   └── test_scheduler.py    # Scheduler tests
└── integration/             # Integration tests
    ├── test_data_sync.py    # End-to-end sync tests
    └── test_database.py     # Database integration tests
```

## Prerequisites

Install testing dependencies:

```bash
pip install -r requirements.txt
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run with Coverage Report

```bash
pytest --cov=src --cov-report=html --cov-report=term
```

Open `htmlcov/index.html` in a browser to view detailed coverage.

### Run Specific Test Categories

**Unit tests only:**
```bash
pytest -m unit
```

**Integration tests only:**
```bash
pytest -m integration
```

**Async tests only:**
```bash
pytest -m asyncio
```

### Run Specific Test Files

```bash
# Test configuration
pytest tests/unit/test_config.py

# Test OAuth client
pytest tests/unit/test_oauth_client.py

# Test data sync integration
pytest tests/integration/test_data_sync.py
```

### Run Specific Test Classes or Functions

```bash
# Run a specific test class
pytest tests/unit/test_models.py::TestUserModel

# Run a specific test function
pytest tests/unit/test_rate_limiter.py::TestRateLimiter::test_rate_limiter_initialization
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Extra Debug Output

```bash
pytest -vv --tb=long
```

### Run Tests in Parallel

```bash
pytest -n auto  # Requires pytest-xdist
```

## Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests (fast, isolated)
- `@pytest.mark.integration` - Integration tests (slower, test multiple components)
- `@pytest.mark.asyncio` - Async tests
- `@pytest.mark.slow` - Slow running tests

### Filter Tests by Markers

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run everything except slow tests
pytest -m "not slow"

# Run unit tests that are not slow
pytest -m "unit and not slow"
```

## Test Coverage

### Current Coverage

The test suite includes:

- **Configuration Tests**: 10 tests
- **Model Tests**: 15+ tests
- **OAuth Client Tests**: 12 tests
- **Token Manager Tests**: 13 tests
- **Rate Limiter Tests**: 13 tests
- **Whoop Client Tests**: 15+ tests
- **Service Tests**: 20+ tests
- **Scheduler Tests**: 10+ tests
- **Integration Tests**: 15+ tests

**Total: 120+ tests**

### Generate Coverage Report

```bash
# Terminal report
pytest --cov=src --cov-report=term-missing

# HTML report
pytest --cov=src --cov-report=html

# XML report (for CI/CD)
pytest --cov=src --cov-report=xml
```

### Coverage Goals

- Overall coverage: > 85%
- Critical modules (auth, api, services): > 90%
- Models: > 95%

## Fixtures

Common fixtures are defined in `conftest.py`:

### Database Fixtures

- `database_url` - Test database URL (SQLite in-memory)
- `engine` - SQLAlchemy engine
- `db_session` - Database session (transaction-based, rolled back after each test)

### Model Fixtures

- `test_user` - Sample user
- `test_oauth_token` - Valid OAuth token
- `expired_oauth_token` - Expired OAuth token
- `test_sleep_record` - Sample sleep record
- `test_recovery_record` - Sample recovery record
- `test_workout_record` - Sample workout record
- `test_cycle_record` - Sample cycle record

### API Mock Fixtures

- `mock_whoop_sleep_response` - Mock Whoop API sleep response
- `mock_whoop_recovery_response` - Mock recovery response
- `mock_whoop_workout_response` - Mock workout response
- `mock_whoop_cycle_response` - Mock cycle response
- `mock_whoop_user_profile` - Mock user profile response

### Utility Fixtures

- `event_loop` - Async event loop
- `fixed_datetime` - Fixed datetime for testing
- `date_range` - Date range tuple

## Writing New Tests

### Unit Test Template

```python
import pytest
from src.module import MyClass

@pytest.mark.unit
class TestMyClass:
    """Tests for MyClass."""

    def test_initialization(self):
        """Test class initialization."""
        obj = MyClass()
        assert obj is not None

    def test_method(self):
        """Test specific method."""
        obj = MyClass()
        result = obj.method()
        assert result == expected_value
```

### Async Test Template

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncClass:
    """Tests for async functionality."""

    async def test_async_method(self):
        """Test async method."""
        obj = AsyncClass()
        result = await obj.async_method()
        assert result is not None
```

### Integration Test Template

```python
import pytest
from src.module import IntegrationClass

@pytest.mark.integration
@pytest.mark.asyncio
class TestIntegration:
    """Integration tests."""

    async def test_end_to_end_flow(self, db_session, test_user):
        """Test complete flow from start to finish."""
        # Setup
        obj = IntegrationClass(user_id=test_user.id)

        # Execute
        result = await obj.do_something()

        # Verify
        assert result is not None
        # Verify database state
        records = db_session.query(Model).all()
        assert len(records) > 0
```

## Mocking

### Mock HTTP Requests

Using `respx` for HTTP mocking:

```python
import respx
import httpx

@respx.mock
async def test_api_call():
    """Test API call with mocked response."""
    respx.get("https://api.example.com/endpoint").mock(
        return_value=httpx.Response(200, json={"data": "test"})
    )

    # Make actual call
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/endpoint")
        assert response.json() == {"data": "test"}
```

### Mock Async Functions

```python
from unittest.mock import AsyncMock, patch

async def test_with_mock():
    """Test with mocked async function."""
    with patch('module.async_function', new=AsyncMock(return_value="mocked")):
        result = await some_function()
        assert result == "expected"
```

## Continuous Integration

Tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pytest --cov=src --cov-report=xml --cov-report=term

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

## Debugging Tests

### Run with pdb Debugger

```bash
pytest --pdb  # Drop into debugger on failure
pytest --pdb --maxfail=1  # Stop on first failure
```

### Print Debug Output

```bash
pytest -s  # Show print statements and logging
```

### Show Local Variables on Failure

```bash
pytest --showlocals
```

## Best Practices

1. **Isolation**: Each test should be independent and not rely on other tests
2. **Fixtures**: Use fixtures for common setup to avoid code duplication
3. **Naming**: Use descriptive test names that explain what is being tested
4. **Assertions**: Use specific assertions with helpful messages
5. **Mocking**: Mock external dependencies (API calls, file I/O)
6. **Coverage**: Aim for high coverage but focus on meaningful tests
7. **Speed**: Keep unit tests fast; use integration tests for slower operations
8. **Documentation**: Add docstrings to test classes and functions

## Troubleshooting

### Tests Fail with Database Errors

- Ensure test database is properly isolated
- Check that transactions are rolled back after each test
- Verify fixtures are using `db_session` fixture

### Async Tests Hanging

- Ensure all async calls use `await`
- Check for missing `@pytest.mark.asyncio` decorator
- Verify event loop is properly configured

### Import Errors

- Ensure `PYTHONPATH` includes project root
- Check that `pytest.ini` has `pythonpath = .`
- Verify all `__init__.py` files exist

### Coverage Not Generated

- Install pytest-cov: `pip install pytest-cov`
- Use `--cov=src` flag
- Check that source files are importable

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [respx](https://lundberg.github.io/respx/)
- [Faker](https://faker.readthedocs.io/)
