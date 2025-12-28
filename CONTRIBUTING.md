# Contributing to Whoopster

Thank you for your interest in contributing to Whoopster! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions. We're all here to build something useful for the Whoop community.

## How to Contribute

### Reporting Bugs

Before creating a bug report:
1. Check the [existing issues](https://github.com/yourusername/whoopster/issues)
2. Try the latest version from the main branch
3. Review the [troubleshooting guide](README.md#troubleshooting)

When submitting a bug report, include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Docker version, Python version)
- Relevant logs (sanitize any credentials)

### Suggesting Features

Feature requests are welcome! Please:
1. Check if the feature has already been suggested
2. Describe the use case and benefits
3. Consider implementation complexity
4. Be open to discussion and alternatives

### Pull Requests

#### Before Starting

1. **Discuss large changes** in an issue first
2. **Check the roadmap** in README.md to see planned work
3. **Look for "good first issue"** labels for beginner-friendly tasks

#### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/yourusername/whoopster.git
cd whoopster

# Create a virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install black isort mypy pytest pytest-cov

# Copy environment template
cp .env.example .env
# Edit .env with your credentials
```

#### Making Changes

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/bug-description
   ```

2. **Write code** following our standards:
   - Follow PEP 8 style guidelines
   - Use type hints (Python 3.11+ syntax)
   - Add docstrings to public functions/classes
   - Keep functions focused and small
   - Write descriptive variable names

3. **Format code** before committing:
   ```bash
   # Format with black
   black src/ tests/

   # Sort imports
   isort src/ tests/

   # Check types
   mypy src/
   ```

4. **Write tests** for new functionality:
   ```bash
   # Run tests
   pytest tests/ -v

   # Check coverage
   pytest tests/ --cov=src --cov-report=html
   ```

5. **Update documentation**:
   - Add docstrings to new functions
   - Update README.md if changing user-facing features
   - Update IMPLEMENTATION.md for architectural changes
   - Add comments for complex logic

6. **Commit with clear messages**:
   ```bash
   git commit -m "Add: Brief description of feature"
   git commit -m "Fix: Brief description of bug fix"
   git commit -m "Docs: Update configuration guide"
   git commit -m "Refactor: Improve data sync logic"
   ```

   Format: `<type>: <description>`

   Types:
   - `Add`: New feature
   - `Fix`: Bug fix
   - `Docs`: Documentation only
   - `Style`: Formatting, no code change
   - `Refactor`: Code restructuring
   - `Test`: Adding tests
   - `Chore`: Maintenance (deps, config)

#### Pull Request Process

1. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request** on GitHub:
   - Use a clear, descriptive title
   - Reference related issues (e.g., "Fixes #123")
   - Describe what changed and why
   - List any breaking changes
   - Add screenshots for UI changes

3. **PR Checklist**:
   - [ ] Code follows style guidelines
   - [ ] Self-review completed
   - [ ] Comments added for complex logic
   - [ ] Documentation updated
   - [ ] Tests added/updated
   - [ ] All tests pass
   - [ ] No new warnings
   - [ ] Migrations created if schema changed

4. **Respond to feedback**:
   - Address review comments promptly
   - Push changes to the same branch
   - Discuss disagreements constructively
   - Request re-review when ready

## Development Guidelines

### Python Style

- **PEP 8** compliance
- **Type hints** for all function signatures
- **Docstrings** for public APIs (Google style)
- **Line length**: 88 characters (Black default)
- **Imports**: Use absolute imports from `src/`

Example:
```python
from typing import Optional
from datetime import datetime

def fetch_sleep_records(
    user_id: int,
    start_date: Optional[datetime] = None
) -> list[SleepRecord]:
    """
    Fetch sleep records for a user.

    Args:
        user_id: Database ID of the user
        start_date: Optional start date filter

    Returns:
        List of sleep records sorted by start time

    Raises:
        ValueError: If user_id is invalid
    """
    # Implementation
```

### Database Changes

When modifying database models:

1. **Update SQLAlchemy model** in `src/models/db_models.py`
2. **Generate migration**:
   ```bash
   alembic revision --autogenerate -m "Add field to table"
   ```
3. **Review migration** in `src/database/migrations/versions/`
4. **Test migration**:
   ```bash
   alembic upgrade head  # Apply
   alembic downgrade -1  # Rollback
   alembic upgrade head  # Re-apply
   ```
5. **Update Pydantic models** if needed
6. **Add migration to PR**

### API Changes

When modifying Whoop API integration:

1. **Update Pydantic models** first
2. **Validate against Whoop API docs**
3. **Handle optional fields** properly
4. **Add error handling** for API failures
5. **Test with real API** (not just mocks)
6. **Update documentation** with new fields

### Testing

Write tests for:
- New features
- Bug fixes
- Edge cases
- Error handling

Test structure:
```python
def test_fetch_sleep_records_success():
    """Test successful sleep record retrieval."""
    # Arrange
    user_id = 1
    expected_count = 5

    # Act
    records = fetch_sleep_records(user_id)

    # Assert
    assert len(records) == expected_count
    assert all(r.user_id == user_id for r in records)
```

### Documentation

Update documentation when:
- Adding new features
- Changing configuration
- Modifying API behavior
- Fixing important bugs
- Adding troubleshooting steps

Documentation files:
- `README.md`: User-facing documentation
- `IMPLEMENTATION.md`: Technical deep-dive
- `STATUS.md`: Current progress (maintainers update)
- Code docstrings: Inline documentation

## Project Structure

Key areas for contributions:

### Core Application (`src/`)
- **models/**: Database and API models
- **auth/**: OAuth 2.0 authentication
- **api/**: Whoop API client
- **services/**: Data sync services
- **database/**: Database layer
- **scheduler/**: Job scheduling
- **utils/**: Utilities and helpers

### Infrastructure
- **docker-compose.yml**: Service orchestration
- **Dockerfile**: Application container
- **alembic/**: Database migrations
- **grafana/**: Dashboard configuration

### Scripts (`scripts/`)
- **init_oauth.py**: OAuth setup
- **test_connection.py**: Connection testing

## Release Process

Maintainers handle releases, but contributors should:
1. **Bump version** in appropriate files
2. **Update CHANGELOG.md** with changes
3. **Tag release** in commit message

Version scheme: `MAJOR.MINOR.PATCH` (Semantic Versioning)

## Getting Help

- **Questions**: [GitHub Discussions](https://github.com/yourusername/whoopster/discussions)
- **Bugs**: [GitHub Issues](https://github.com/yourusername/whoopster/issues)
- **Whoop API**: [developer.whoop.com](https://developer.whoop.com/)

## Recognition

Contributors will be:
- Listed in README.md acknowledgments
- Credited in release notes
- Thanked in relevant PRs/issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for making Whoopster better! 🎉
