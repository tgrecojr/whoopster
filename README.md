# Whoopster 🏃‍♂️

> Automated Whoop data collection and visualization platform

Whoopster automatically syncs your Whoop wearable data (sleep, recovery, workouts, and physiological cycles) to a PostgreSQL database and visualizes it through beautiful Grafana dashboards.

![Status](https://img.shields.io/badge/status-production--ready-green)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-required-blue)

## What is Whoopster?

Whoopster is a self-hosted data pipeline that:
- 🔄 Automatically fetches your Whoop data every 15 minutes via OAuth 2.0
- 💾 Stores everything in PostgreSQL with full history
- 📊 Provides pre-built Grafana dashboards for visualization
- 🐳 Runs entirely in Docker with zero configuration hassle
- 🔒 Keeps your health data private and under your control

## Features

### What Data Gets Synced
- **Sleep Tracking**: Sleep stages (light, deep, REM), performance scores, efficiency, respiratory rate
- **Recovery Metrics**: Recovery score, HRV (RMSSD), resting heart rate, SpO2, skin temperature
- **Workout Data**: Strain scores, heart rate zones, distance, calories, 100+ sport types
- **Daily Cycles**: Overall strain, heart rate trends, energy expenditure

### Key Capabilities
- 🔐 **Secure & Private**: OAuth 2.0 authentication, encrypted tokens, all data stays on your server
- 🔄 **Automatic Sync**: Fetches new data every 15 minutes (configurable)
- 📊 **Historical Data**: Backfill your complete Whoop history with one command
- 📈 **Visualization**: Grafana dashboards to analyze your health trends
- 🗄️ **Complete History**: PostgreSQL database stores all your data forever
- 🔍 **Raw Data Access**: Full API responses stored for custom analysis
- 🐳 **Easy Setup**: Docker Compose handles everything

## Architecture

```
┌─────────────────┐
│   Whoop API     │ ← OAuth 2.0 with PKCE
│   (v2 REST)     │    Automatic token refresh
└────────┬────────┘
         │
         │ Sync every 15 minutes
         │ Rate limited, retries with backoff
         │
    ┌────▼─────┐
    │ Whoopster│
    │   App    │ ← Python 3.11 + SQLAlchemy + Pydantic
    │          │   APScheduler for jobs
    └────┬─────┘
         │
         │ UPSERT operations
         │ UUID-based deduplication
         │
    ┌────▼─────────┐
    │ PostgreSQL   │ ← 7 tables, UUID keys
    │   Database   │   Alembic migrations
    └────┬─────────┘
         │
         │ SQL queries (manual datasource setup)
         │
    ┌────▼─────────┐
    │   Grafana    │ ← Manual configuration required
    │  Dashboards  │   Import pre-built JSON dashboards
    └──────────────┘
```

## Prerequisites

### Required
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [Whoop device and membership](https://www.whoop.com/)
- [Whoop Developer account](https://developer.whoop.com/) (free)

### Optional (for local development)
- Python 3.11+
- PostgreSQL 15+

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/whoopster.git
cd whoopster
```

### 2. Set Up Whoop Developer App

1. Go to [developer.whoop.com](https://developer.whoop.com/)
2. Create a new application
3. Set redirect URI to `http://localhost:8000/callback`
4. Copy your Client ID and Client Secret
5. Required scopes: `read:sleep`, `read:workout`, `read:recovery`, `read:cycles`, `offline`

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in the required variables:

```bash
# Whoop API credentials (from developer.whoop.com)
WHOOP_CLIENT_ID=your_client_id_here
WHOOP_CLIENT_SECRET=your_client_secret_here

# Passwords
POSTGRES_PASSWORD=choose_a_secure_password
GRAFANA_ADMIN_PASSWORD=choose_a_secure_password

# Generate encryption key with this command:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEY=your_generated_key_here
```

**Generate the encryption key** (required for OAuth token security):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output and paste it as `TOKEN_ENCRYPTION_KEY` in your `.env` file.

See the [Configuration](#configuration) section for detailed documentation on all environment variables.

### 4. Start Services

```bash
docker-compose up -d
```

This starts:
- **PostgreSQL** on `localhost:5432`
- **Whoopster app** (data sync service)
- **Grafana** on `http://localhost:3000` (requires manual setup - see step 6)

The app automatically:
- Runs database migrations on startup
- Starts the sync scheduler
- Begins fetching data every 15 minutes

### 5. Authorize Whoop Access (Required Before First Use)

#### Option A: With Browser (Local Machine)

```bash
docker-compose exec app python scripts/init_oauth.py
```

This will:
1. Create a user record in the database
2. Open your browser to Whoop's authorization page
3. Ask you to grant permissions
4. Store OAuth tokens securely in the database
5. Enable automatic token refresh

#### Option B: Headless Mode (Remote Server)

For headless servers without a browser (SSH, VPS, etc.):

```bash
docker-compose exec app python scripts/init_oauth.py --headless
```

This will:
1. Display an authorization URL
2. You copy the URL and open it on ANY device (phone, laptop, etc.)
3. After authorizing, Whoop redirects to a callback URL
4. You copy the **entire callback URL** and paste it back into the terminal
5. Tokens are stored in the database

**Example Headless Flow**:
```
======================================================================
AUTHORIZATION URL
======================================================================

Copy this URL and open it in a browser on ANY device:

https://api.prod.whoop.com/oauth/oauth2/auth?client_id=...

======================================================================

Step 2: After authorizing, you'll be redirected to a callback URL.
         The URL will look like:
         http://localhost:8000/callback?code=XXXXX&state=XXXXX

         Copy the ENTIRE callback URL and paste it below.

Paste the full callback URL here: _
```

**⚠️ Important**: You must complete this step before:
- Using the backfill script
- Running manual syncs
- Letting the automatic sync run

### 6. Set Up Grafana (Manual Configuration)

Grafana is included for data visualization, but requires manual setup:

1. **Access Grafana**:
   - Open [http://localhost:3000](http://localhost:3000) in your browser
   - Login with:
     - **Username**: `admin` (or your `GRAFANA_ADMIN_USER` from `.env`)
     - **Password**: Your `GRAFANA_ADMIN_PASSWORD` from `.env`

2. **Add PostgreSQL Datasource**:
   - Click **⚙️ (Settings)** → **Data sources** → **Add data source**
   - Select **PostgreSQL**
   - Configure:
     - **Name**: `Whoopster PostgreSQL` (or any name you prefer)
     - **Host**: `postgres:5432`
     - **Database**: Value from `POSTGRES_DB` in `.env` (default: `whoopster`)
     - **User**: Value from `POSTGRES_USER` in `.env` (default: `whoopster`)
     - **Password**: Value from `POSTGRES_PASSWORD` in `.env`
     - **TLS/SSL Mode**: `disable`
     - **Version**: `15.0+`
   - Click **Save & test** to verify connection

3. **Import Pre-built Dashboard**:
   - Click **+ (Plus)** → **Import dashboard**
   - Click **Upload JSON file**
   - Select `grafana/dashboards/whoop-overview.json` from the repository
   - When prompted, select your PostgreSQL datasource
   - Click **Import**

4. **Run OAuth Setup** (if not done already):
   ```bash
   docker-compose exec app python scripts/init_oauth.py
   ```

5. **Wait for Data**:
   - First sync runs automatically every 15 minutes
   - Or trigger manual sync (see [Usage](#usage) section)
   - Refresh your dashboard to see data appear

See the [Grafana Setup](#grafana-setup) section below for detailed configuration instructions and dashboard information.

## Project Structure

```
whoopster/
├── src/                        # Application source code
│   ├── models/                 # SQLAlchemy & Pydantic models
│   │   ├── db_models.py        # Database schema (7 tables)
│   │   └── api_models.py       # API response validation
│   ├── auth/                   # OAuth 2.0 client & token management
│   │   ├── oauth_client.py     # OAuth flow with PKCE
│   │   └── token_manager.py    # Auto-refresh, token storage
│   ├── api/                    # Whoop API client & rate limiting
│   │   ├── whoop_client.py     # API client with pagination
│   │   └── rate_limiter.py     # Sliding window rate limiter
│   ├── services/               # Data sync services
│   │   ├── data_collector.py   # Main sync orchestrator
│   │   ├── sleep_service.py    # Sleep data sync
│   │   ├── recovery_service.py # Recovery data sync
│   │   ├── workout_service.py  # Workout data sync
│   │   └── cycle_service.py    # Cycle data sync
│   ├── database/               # Database management
│   │   ├── session.py          # DB session management
│   │   └── migrations/         # Alembic migration scripts
│   ├── scheduler/              # Job scheduling
│   │   └── job_scheduler.py    # APScheduler with PostgreSQL store
│   ├── utils/                  # Utilities
│   │   └── logging_config.py   # Structured logging
│   ├── config.py               # Application configuration
│   └── main.py                 # Application entry point
│
├── scripts/                    # Utility scripts
│   ├── init_oauth.py           # Interactive OAuth setup
│   ├── backfill_data.py        # Historical data backfill
│   └── test_connection.py      # Connection testing
│
├── tests/                      # Test suite (132 tests)
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   ├── conftest.py             # Pytest fixtures
│   └── README.md               # Testing documentation
│
├── grafana/                    # Grafana dashboards
│   └── dashboards/             # Pre-built dashboard JSON files for import
│
├── docs/                       # Documentation
│   ├── ARCHITECTURE.md         # System architecture
│   ├── TESTING.md              # Testing guide
│   └── DEPLOYMENT.md           # Deployment guide
│
├── docker-compose.yml          # Multi-container orchestration
├── Dockerfile                  # Application container
├── requirements.txt            # Python dependencies
├── alembic.ini                 # Database migration config
├── pytest.ini                  # Test configuration
├── .env.example                # Environment template
└── README.md                   # This file
```

## Database Schema

Whoopster stores data in 7 PostgreSQL tables:

| Table | Description | Key Fields |
|-------|-------------|------------|
| `users` | User information | whoop_user_id, email |
| `oauth_tokens` | OAuth access/refresh tokens | access_token, refresh_token, expires_at |
| `sleep_records` | Sleep data | sleep stages, performance, efficiency, respiratory_rate |
| `recovery_records` | Recovery metrics | recovery_score, hrv_rmssd, resting_heart_rate, spo2 |
| `workout_records` | Workout activities | strain_score, sport_id, hr_zones, distance |
| `cycle_records` | Physiological cycles | daily_strain, avg_heart_rate, kilojoules |
| `sync_status` | Sync tracking | last_sync_time, last_record_time, records_fetched |

**Key Design Decisions**:
- UUID primary keys matching Whoop's IDs for natural deduplication
- UPSERT operations (`ON CONFLICT DO UPDATE`) for idempotent syncs
- UTC timestamps throughout, original timezone preserved in `timezone_offset`
- JSONB `raw_data` column stores complete API responses for debugging
- Incremental sync via `last_record_time` tracking

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed schema documentation.

## Configuration

### Environment Variables

Whoopster uses environment variables for all configuration. All settings are managed through a `.env` file in the project root.

#### Initial Setup

1. **Copy the template**:
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` and configure required variables** (see below)

3. **Verify configuration**:
   ```bash
   # Test that all required variables are set
   docker-compose run --rm app python -c "from src.config import settings; print('✓ Configuration valid')"
   ```

If you get an error about missing environment variables, the error message will clearly indicate which variables need to be set.

#### Required Variables

These variables **must** be configured before starting Whoopster:

| Variable | Description | How to Get |
|----------|-------------|------------|
| `POSTGRES_PASSWORD` | Database password | Choose a strong password (20+ chars recommended) |
| `WHOOP_CLIENT_ID` | OAuth client ID | Get from [developer.whoop.com](https://developer.whoop.com/) |
| `WHOOP_CLIENT_SECRET` | OAuth client secret | Get from [developer.whoop.com](https://developer.whoop.com/) |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password | Choose a strong password |
| `TOKEN_ENCRYPTION_KEY` | Fernet encryption key for OAuth tokens | Generate using command below |

#### Generating the Encryption Key

The `TOKEN_ENCRYPTION_KEY` is used to encrypt OAuth tokens at rest in the database. This is a **required security feature**.

**Generate a new key**:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Example output:
```
kvxTPIk48sGyVT4OO_rNDdmpFwSsSJmA5Z3wGiX9vKA=
```

Add this to your `.env` file:
```bash
TOKEN_ENCRYPTION_KEY=your_generated_encryption_key_here
```

**Important Security Notes**:
- ⚠️ **Keep this key secure** - treat it like a password
- ⚠️ **Never commit it to version control** - `.env` is in `.gitignore`
- ⚠️ **If you change this key**, existing encrypted tokens will become unreadable and users will need to re-authorize
- ⚠️ **Backup this key** if you backup your database - you'll need it to decrypt tokens

#### Optional Variables

These have sensible defaults but can be customized:

```bash
# PostgreSQL Configuration
POSTGRES_DB=whoopster                 # Database name (default: whoopster)
POSTGRES_USER=whoopster               # Database user (default: whoopster)
POSTGRES_HOST=postgres                # Docker service name, or external host
POSTGRES_PORT=5432                    # PostgreSQL port (default: 5432)

# Whoop API Endpoints (rarely need to change)
WHOOP_REDIRECT_URI=http://localhost:8000/callback
WHOOP_API_BASE_URL=https://api.prod.whoop.com

# Application Settings
LOG_LEVEL=INFO                        # Logging level: DEBUG, INFO, WARNING, ERROR
SYNC_INTERVAL_MINUTES=15              # How often to sync data (default: 15)
ENVIRONMENT=development               # development or production
MAX_REQUESTS_PER_MINUTE=60            # Whoop API rate limit (default: 60)

# Grafana
GRAFANA_ADMIN_USER=admin              # Grafana admin username (default: admin)
```

#### Complete `.env` Example

Here's a complete example with all required variables filled in:

```bash
# PostgreSQL Configuration
POSTGRES_DB=whoopster
POSTGRES_USER=whoopster
POSTGRES_PASSWORD=my_super_secure_database_password_2024
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Whoop API Credentials (from developer.whoop.com)
WHOOP_CLIENT_ID=your_client_id_here
WHOOP_CLIENT_SECRET=your_client_secret_here
WHOOP_REDIRECT_URI=http://localhost:8000/callback

# Application Configuration
LOG_LEVEL=INFO
SYNC_INTERVAL_MINUTES=15
ENVIRONMENT=development

# Grafana Configuration
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=my_grafana_password_2024

# Security Configuration (REQUIRED)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEY=your_generated_encryption_key_here

# Optional: Rate Limiting
MAX_REQUESTS_PER_MINUTE=60
```

#### Running Locally (Outside Docker)

If you're running Whoopster locally without Docker, environment variables are loaded automatically from `.env` using `python-dotenv`. Simply ensure your `.env` file is in the project root:

```bash
# Activate virtual environment
source venv/bin/activate

# Run the app (automatically loads .env)
python -m src.main

# Or run from any directory (also works)
cd /some/other/directory
python -m /path/to/whoopster/src.main  # Still finds .env correctly
```

The application uses `python-dotenv` to ensure the `.env` file is loaded from the project root regardless of your current working directory.

#### Configuration Error Messages

If you're missing required environment variables, you'll see a clear error message:

```
======================================================================
CONFIGURATION ERROR: Missing or invalid environment variables
======================================================================

Missing required environment variables:
  - TOKEN_ENCRYPTION_KEY
  - POSTGRES_PASSWORD

Please update your .env file at: /path/to/whoopster/.env
You can use .env.example as a template: /path/to/whoopster/.env.example

For TOKEN_ENCRYPTION_KEY, generate a new key with:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
======================================================================
```

This makes it easy to identify and fix configuration issues.

## Usage

### Backfill Historical Data

By default, Whoopster syncs data incrementally (only new data since the last sync). To fetch historical data from before you set up Whoopster, use the backfill script.

**⚠️ Prerequisites**: You must run OAuth setup first (step 5 in Quick Start) before backfilling data.

#### Backfill Last N Days

```bash
# Get last 30 days of data
docker-compose exec app python -m scripts.backfill_data --days 30

# Get last 6 months
docker-compose exec app python -m scripts.backfill_data --days 180

# Get last year
docker-compose exec app python -m scripts.backfill_data --days 365
```

#### Backfill Specific Date Range

```bash
# Get data from specific month
docker-compose exec app python -m scripts.backfill_data --start 2024-06-01 --end 2024-06-30

# Get data from last year
docker-compose exec app python -m scripts.backfill_data --start 2024-01-01 --end 2024-12-31
```

#### Backfill Specific Data Types

```bash
# Get only sleep and recovery data from last 90 days
docker-compose exec app python -m scripts.backfill_data --days 90 --types sleep recovery

# Get only workouts from specific date range
docker-compose exec app python -m scripts.backfill_data --start 2024-01-01 --end 2024-12-31 --types workout
```

#### Backfill ALL Historical Data

```bash
# Fetch complete Whoop history (can take a while!)
docker-compose exec app python -m scripts.backfill_data --all
```

**Important Notes**:
- Backfill respects Whoop's rate limits (automatically throttles requests)
- Large backfills (1+ years) can take 10-30 minutes depending on data volume
- The `--all` option fetches your complete Whoop history since you started using the device
- Backfill uses upsert operations, so it's safe to re-run (won't create duplicates)

### View Logs

```bash
# Follow app logs
docker-compose logs -f app

# View all service logs
docker-compose logs -f

# Filter by log level
docker-compose logs app | grep ERROR
```

### Check Sync Status

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U whoopster -d whoopster

# Query sync status
SELECT
  data_type,
  last_sync_time,
  status,
  records_fetched,
  error_message
FROM sync_status
ORDER BY last_sync_time DESC;

# Check recent sleep records
SELECT
  start_time::date as date,
  sleep_performance_percentage,
  score_state
FROM sleep_records
ORDER BY start_time DESC
LIMIT 10;
```

### Manual Data Sync

```bash
# Trigger immediate sync for all data types
docker-compose exec app python -c "
import asyncio
from src.services.data_collector import sync_user_data
asyncio.run(sync_user_data(user_id=1))
"

# Sync specific data type
docker-compose exec app python -c "
import asyncio
from src.services.sleep_service import SleepService
from src.api.whoop_client import WhoopClient
asyncio.run(SleepService(user_id=1, whoop_client=WhoopClient(user_id=1)).sync_sleep_records())
"
```

### Database Migrations

```bash
# View current migration version
docker-compose exec app alembic current

# View migration history
docker-compose exec app alembic history

# Create new migration after model changes
docker-compose exec app alembic revision --autogenerate -m "Add new column"

# Apply migrations
docker-compose exec app alembic upgrade head

# Rollback one migration
docker-compose exec app alembic downgrade -1
```

## Development

### Local Setup

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up pre-commit hooks (optional)
pip install pre-commit
pre-commit install

# Run locally (requires PostgreSQL running)
export $(cat .env | xargs)
python -m src.main
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_whoop_client.py -v
```

The test suite includes 132 tests covering data sync, OAuth flow, API client, and database operations. See [docs/TESTING.md](docs/TESTING.md) for details.

### Code Quality

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/ tests/
```

## Grafana Setup

Whoopster includes Grafana for data visualization, but it requires **manual configuration** to connect to your database and import dashboards.

### Step 1: Configure PostgreSQL Datasource

After starting services with `docker-compose up -d`:

1. **Access Grafana**: Navigate to http://localhost:3000
2. **Login**: Use credentials from your `.env` file
   - Username: `admin` (default)
   - Password: Your `GRAFANA_ADMIN_PASSWORD`

3. **Add Datasource**:
   - Click **⚙️ Configuration** (gear icon) → **Data sources**
   - Click **Add data source**
   - Select **PostgreSQL**

4. **Configure Connection**:
   ```
   Name: Whoopster PostgreSQL (or any name you prefer)
   Host: postgres:5432
   Database: whoopster (or your POSTGRES_DB value)
   User: whoopster (or your POSTGRES_USER value)
   Password: <your POSTGRES_PASSWORD>
   TLS/SSL Mode: disable
   PostgreSQL Version: 15.0+
   ```

5. **Test & Save**:
   - Click **Save & test**
   - You should see: ✅ "Database Connection OK"

### Step 2: Import Dashboard

Whoopster includes a pre-built **Whoop Overview Dashboard** with 11 panels.

**Import Instructions**:

1. **Navigate to Import**:
   - Click **+ (Plus icon)** in the left sidebar
   - Select **Import dashboard**

2. **Upload JSON**:
   - Click **Upload JSON file**
   - Select `grafana/dashboards/whoop-overview.json` from the repository
   - Or copy the contents and paste into the text area

3. **Select Datasource**:
   - When prompted for **PostgreSQL Datasource**, select the datasource you created
   - Click **Import**

4. **View Dashboard**:
   - The dashboard will open automatically
   - Access it anytime from **Dashboards** → **Whoop Overview Dashboard**

### Available Dashboard Panels

The **Whoop Overview Dashboard** includes:

#### Summary Statistics (4 panels)
- **Total Sleep Records**: Count of all sleep sessions
- **Total Workouts**: Count of all activities
- **Latest Recovery Score**: Most recent recovery percentage
- **Latest Daily Strain**: Most recent daily strain value

#### Time Series Visualizations (6 panels)
- **Sleep Performance Trend**: Sleep quality over time (percentage)
- **Recovery Score Trend**: Daily recovery patterns
- **Resting Heart Rate Trend**: Cardiovascular fitness indicator
- **HRV Trend**: Heart Rate Variability (RMSSD) for stress/recovery
- **Workout Strain**: Strain from workouts over time
- **Daily Strain Trend**: Cumulative daily stress patterns

#### Activity Analysis (1 panel)
- **Workouts by Sport**: Pie chart of workout type distribution

### Customizing Dashboards

All dashboards are fully editable:

- **Time Range**: Use picker in top-right to adjust date range
- **Refresh Rate**: Set auto-refresh intervals for real-time updates
- **Edit Panels**: Click panel title → **Edit** to modify queries/visualizations
- **Save Changes**: Click 💾 save icon to persist modifications

### Creating Custom Dashboards

Build your own dashboards using the PostgreSQL datasource:

1. **Create Dashboard**: Click **+ → Dashboard**
2. **Add Panel**: Click **Add visualization**
3. **Select Datasource**: Choose your PostgreSQL datasource
4. **Write SQL Query**: Query against these tables:
   - `sleep_records` - Sleep data with stages and performance
   - `recovery_records` - Recovery metrics (HRV, RHR, SpO2)
   - `workout_records` - Workout activities and strain
   - `cycle_records` - Physiological cycles and daily strain

**Example Query** (Sleep Performance):
```sql
SELECT
  start_time AS time,
  sleep_performance_percentage
FROM sleep_records
WHERE $__timeFilter(start_time)
ORDER BY start_time
```

**Example Query** (Recovery Score):
```sql
SELECT
  created_at AS time,
  recovery_score
FROM recovery_records
WHERE $__timeFilter(created_at)
ORDER BY created_at
```

**Example Query** (Workout Count by Sport):
```sql
SELECT
  sport_id,
  COUNT(*) as count
FROM workout_records
WHERE $__timeFilter(start_time)
GROUP BY sport_id
ORDER BY count DESC
```

### Dashboard Files

Pre-built dashboards are located in `grafana/dashboards/`:
- `whoop-overview.json` - Main overview dashboard with 11 summary panels
- `whoop-sleep.json` - Detailed sleep analysis with 9 panels (sleep stages, performance, efficiency)
- `whoop-recovery.json` - Recovery metrics with 8 panels (recovery score, HRV, resting HR, SpO2)
- `whoop-workout.json` - Workout analysis with 8 panels (strain, HR zones, sport breakdown)
- `whoop-cycle.json` - Daily cycle/strain analysis with 9 panels (strain trends, energy expenditure)

All dashboard files use datasource placeholders, allowing you to select your own datasource during import.

### Troubleshooting Grafana

See the [Troubleshooting](#troubleshooting) section for common Grafana issues:
- Cannot access Grafana
- Datasource connection errors
- Missing data in dashboards

## Features Status

### ✅ Currently Available

**Core Functionality**:
- ✅ Automatic data sync every 15 minutes (sleep, recovery, workouts, cycles)
- ✅ OAuth 2.0 authentication with automatic token refresh
- ✅ Historical data backfill (fetch all your past Whoop data)
- ✅ Secure token encryption at rest
- ✅ PostgreSQL database with complete data history
- ✅ Docker Compose deployment (one command setup)
- ✅ Rate limiting (respects Whoop API limits)
- ✅ Structured logging with detailed context

**Visualization**:
- ✅ Grafana integration (manual setup)
- ✅ Pre-built Whoop Overview Dashboard (11 panels)
- ✅ Custom dashboard creation (SQL queries)

**Data Management**:
- ✅ Incremental sync (only fetches new data)
- ✅ Upsert operations (no duplicates)
- ✅ Raw JSON storage (complete API responses)
- ✅ Database migrations (Alembic)

### 🚀 Planned Features

**v1.1.0 - Enhanced Usability**:
- Multi-user support
- Web UI for setup and configuration
- Additional pre-built Grafana dashboards
- Custom alerts (low recovery, high strain)
- Data export (CSV, JSON)

**v2.0.0 - Advanced Analytics**:
- Whoop webhooks (real-time updates)
- Advanced analytics and correlations
- Mobile-optimized dashboards
- REST API for data access

## Troubleshooting

### Backfill errors (user not found / foreign key violation)

If you see errors like:
```
❌ ERROR: User Not Found
User ID 1 does not exist in the database.
```

Or:
```
ForeignKeyViolation: insert or update on table "sync_status" violates foreign key constraint
Key (user_id)=(1) is not present in table "users"
```

**Solution**: You need to run OAuth setup first:
```bash
docker-compose exec app python scripts/init_oauth.py
```

This creates the user record and authorizes Whoop access. After OAuth setup completes, you can run the backfill script.

### Configuration errors (missing environment variables)

If you see an error like:
```
ValidationError: 1 validation error for Settings
token_encryption_key
  Field required [type=missing, ...]
```

Or the new user-friendly error:
```
CONFIGURATION ERROR: Missing or invalid environment variables
```

**Solution**:
1. Check that your `.env` file exists in the project root
2. Verify all required variables are set (see [Configuration](#configuration))
3. For `TOKEN_ENCRYPTION_KEY`, generate a new key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
4. Verify your configuration loads correctly:
   ```bash
   docker-compose run --rm app python -c "from src.config import settings; print('✓ Valid')"
   ```

### OAuth tokens expired

```bash
# Re-run OAuth setup
docker-compose exec app python scripts/init_oauth.py

# Check token status
docker-compose exec app python -c "
import asyncio
from src.auth.token_manager import TokenManager
asyncio.run(TokenManager().get_token_info(user_id=1))
"
```

### Sync not running

```bash
# Check app logs for errors
docker-compose logs -f app | grep ERROR

# Verify scheduler is running
docker-compose exec app python -c "
from src.scheduler.job_scheduler import get_scheduler
scheduler = get_scheduler()
print('Scheduler running:', scheduler.scheduler.running)
print('Jobs:', scheduler.get_all_jobs())
"

# Check sync status in database
docker-compose exec postgres psql -U whoopster -d whoopster \
  -c "SELECT * FROM sync_status ORDER BY last_sync_time DESC;"
```

### Database connection failed

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
docker-compose exec postgres pg_isready -U whoopster

# Check credentials
docker-compose exec app python scripts/test_connection.py

# View database logs
docker-compose logs postgres
```

### Cannot access Grafana

If you can't access http://localhost:3000:

```bash
# Check if Grafana container is running
docker-compose ps grafana

# Check Grafana logs
docker-compose logs grafana

# Restart Grafana
docker-compose restart grafana

# Check if port 3000 is already in use
lsof -i :3000  # On macOS/Linux
netstat -ano | findstr :3000  # On Windows
```

**Common issues**:
- **Port conflict**: Change Grafana port in `docker-compose.yml` (line 85: `"3000:3000"` → `"3001:3000"`)
- **Container not healthy**: Check logs for errors, ensure PostgreSQL is running
- **Wrong credentials**: Verify `GRAFANA_ADMIN_PASSWORD` in `.env` matches what you're entering

### Grafana datasource not connecting

If you're unable to connect the PostgreSQL datasource in Grafana:

```bash
# Verify PostgreSQL is accessible from Grafana container
docker-compose exec grafana nc -zv postgres 5432

# Check PostgreSQL credentials
docker-compose exec postgres psql -U whoopster -d whoopster -c "\dt"

# Test connection from command line
docker-compose exec grafana psql -h postgres -U whoopster -d whoopster
```

**Common issues**:
- **Wrong host**: Use `postgres:5432` not `localhost:5432` (Docker service name)
- **Wrong credentials**: Verify `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` from `.env`
- **PostgreSQL not ready**: Wait for postgres to be healthy, then try again
- **TLS/SSL mode**: Ensure it's set to `disable` in datasource settings

### Missing data in Grafana

If dashboards show "No Data":

```bash
# Check sync_status table
docker-compose exec postgres psql -U whoopster -d whoopster \
  -c "SELECT data_type, last_sync_time, status, records_fetched, error_message
      FROM sync_status ORDER BY last_sync_time DESC;"

# Check if records exist
docker-compose exec postgres psql -U whoopster -d whoopster \
  -c "SELECT COUNT(*) FROM sleep_records;
      SELECT COUNT(*) FROM recovery_records;
      SELECT COUNT(*) FROM workout_records;"

# Verify OAuth is set up
docker-compose exec postgres psql -U whoopster -d whoopster \
  -c "SELECT user_id, expires_at FROM oauth_tokens;"

# If no OAuth tokens, run setup
docker-compose exec app python scripts/init_oauth.py

# Trigger manual sync
docker-compose exec app python -c "
import asyncio
from src.services.data_collector import sync_user_data
asyncio.run(sync_user_data(user_id=1))
"
```

**Common causes**:
- OAuth not configured (run `scripts/init_oauth.py`)
- No sync has run yet (wait 15 minutes or trigger manually)
- Time range filter in dashboard doesn't match your data (adjust date range)
- Data sync failed (check app logs: `docker-compose logs app | grep ERROR`)

### Rate limiting issues

```bash
# Check rate limiter stats
docker-compose exec app python -c "
import asyncio
from src.api.rate_limiter import RateLimiter
limiter = RateLimiter()
stats = asyncio.run(limiter.get_stats())
print(f'Requests in window: {stats[\"requests_in_window\"]}/{stats[\"max_requests\"]}')
print(f'Utilization: {stats[\"utilization_percent\"]:.1f}%')
"

# Adjust rate limit in .env
# MAX_REQUESTS_PER_MINUTE=60 (default with 0.9 safety margin = 54 effective)
```

### Test failures

```bash
# Run tests with verbose output
pytest -vv --tb=short

# Run specific failing test
pytest tests/path/to/test.py::TestClass::test_method -vv

# Check test database
ls -la .test_db.sqlite  # Should be created/deleted per test

# Clear pytest cache
rm -rf .pytest_cache
pytest --cache-clear
```

## Performance Tips

1. **Optimize Sync Interval**: Adjust `SYNC_INTERVAL_MINUTES` based on your needs (default: 15 minutes)
2. **Database Indexing**: Indexes on `user_id` and `start_time` already created
3. **Grafana Query Limits**: Use time range filters in dashboards
4. **Log Levels**: Set `LOG_LEVEL=WARNING` in production to reduce log volume
5. **PostgreSQL Tuning**: Adjust `shared_buffers` and `work_mem` for large datasets

## Security

### Best Practices
- ✅ OAuth tokens stored encrypted in PostgreSQL
- ✅ Never commit `.env` files or credentials
- ✅ All API communication uses HTTPS
- ✅ Database credentials configurable via environment
- ✅ Rate limiting prevents API abuse
- ✅ Structured logging avoids credential leakage

### Security Checklist
- [ ] Use strong passwords for `POSTGRES_PASSWORD` and `GRAFANA_ADMIN_PASSWORD`
- [ ] Rotate OAuth tokens periodically
- [ ] Keep Docker images updated
- [ ] Review logs for suspicious activity
- [ ] Backup database regularly
- [ ] Use firewall rules to restrict database access

To report security vulnerabilities, please email security@example.com.

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`pytest`)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Whoop](https://www.whoop.com/) for their excellent API and developer program
- [SQLAlchemy](https://www.sqlalchemy.org/) for powerful ORM capabilities
- [Pydantic](https://docs.pydantic.dev/) for data validation
- [Grafana](https://grafana.com/) for beautiful visualizations
- [APScheduler](https://apscheduler.readthedocs.io/) for reliable job scheduling
- [httpx](https://www.python-httpx.org/) for async HTTP client
- [pytest](https://pytest.org/) for excellent testing framework

## Support

- **Documentation**:
  - [Architecture Guide](docs/ARCHITECTURE.md)
  - [Testing Guide](docs/TESTING.md)
  - [Deployment Guide](docs/DEPLOYMENT.md)
- **Issues**: [GitHub Issues](https://github.com/yourusername/whoopster/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/whoopster/discussions)
- **Whoop API Docs**: [developer.whoop.com](https://developer.whoop.com/)

## FAQ

**Q: How much data does Whoopster store?**
A: It stores all your historical Whoop data. Expect ~1MB per month of active use.

**Q: Can I get my historical Whoop data from before I set up Whoopster?**
A: Yes! Use the backfill script: `docker-compose exec app python -m scripts.backfill_data --all`. This fetches your complete Whoop history. You can also specify date ranges like `--days 365` for the last year.

**Q: How far back does Whoop data go?**
A: Whoop stores your complete history since you started using the device. The backfill script can fetch all of it.

**Q: Can I run this on a headless server (no browser)?**
A: Yes! Use headless mode for OAuth: `docker-compose exec app python scripts/init_oauth.py --headless`. This lets you authorize on your phone/laptop and paste the callback URL back into the terminal.

**Q: Can I run this on a Raspberry Pi?**
A: Yes! Docker images support ARM64 architecture. Use a Pi 4 or newer for best performance.

**Q: Does this work with Whoop 3.0 or only 4.0?**
A: Works with any Whoop device as long as you have an active membership and API access.

**Q: How often does data sync?**
A: Every 15 minutes by default. Configurable via `SYNC_INTERVAL_MINUTES`.

**Q: What happens if my Whoop membership expires?**
A: Syncing will stop, but your historical data remains in the database.

**Q: Can multiple users share one Whoopster instance?**
A: Schema supports multi-user, but UI for it is planned for v1.1.0.

**Q: Is my data private?**
A: Yes! Everything runs locally on your infrastructure. No data is sent to third parties.

---

**Made with ❤️ by athletes, for athletes**

*Whoopster is not affiliated with or endorsed by Whoop. All product names, logos, and brands are property of their respective owners.*
