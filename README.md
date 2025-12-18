# Whoopster 🏃‍♂️

> Automated Whoop data collection and visualization platform

Whoopster automatically syncs your Whoop wearable data (sleep, recovery, workouts, and physiological cycles) to a PostgreSQL database and visualizes it through beautiful Grafana dashboards.

![Status](https://img.shields.io/badge/status-in%20development-yellow)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## What is Whoopster?

Whoopster is a self-hosted data pipeline that:
- 🔄 Automatically fetches your Whoop data every 15 minutes via OAuth 2.0
- 💾 Stores everything in PostgreSQL with full history
- 📊 Provides pre-built Grafana dashboards for visualization
- 🐳 Runs entirely in Docker with zero configuration hassle
- 🔒 Keeps your health data private and under your control

## Features

### Data Collection
- ✅ **Sleep Tracking**: Sleep stages, performance, efficiency, respiratory rate
- ✅ **Recovery Metrics**: Recovery score, HRV (RMSSD), resting heart rate, SpO2, skin temperature
- ✅ **Workout Data**: Strain scores, heart rate zones, distance, kilojoules, 100+ sport types
- ✅ **Physiological Cycles**: Daily strain, heart rate trends, energy expenditure

### Technical Features
- 🔐 Secure OAuth 2.0 authentication with Whoop API
- 🔄 Incremental data syncs (only fetches new data after initial sync)
- 📈 Time-series optimized PostgreSQL storage
- 🎨 Pre-built Grafana dashboards with best-practice queries
- 🗄️ Alembic database migrations for schema versioning
- 📝 Structured JSON logging for production monitoring
- 🚀 Automatic retry logic with exponential backoff
- ⚡ Rate limiting (respects Whoop API limits)
- 🔍 Raw JSON storage for future-proofing and debugging

## Architecture

```
┌─────────────────┐
│   Whoop API     │ ← OAuth 2.0 Authentication
│   (v2 REST)     │
└────────┬────────┘
         │
         │ Every 15 minutes
         │
    ┌────▼─────┐
    │ Whoopster│
    │   App    │ ← Python 3.11 + SQLAlchemy + Pydantic
    └────┬─────┘
         │
    ┌────▼─────────┐
    │ PostgreSQL   │ ← Time-series data storage
    │   Database   │
    └────┬─────────┘
         │
    ┌────▼─────────┐
    │   Grafana    │ ← Visualization dashboards
    │  Dashboards  │
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

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your Whoop credentials:

```bash
WHOOP_CLIENT_ID=your_client_id_here
WHOOP_CLIENT_SECRET=your_client_secret_here
POSTGRES_PASSWORD=choose_a_secure_password
GRAFANA_ADMIN_PASSWORD=choose_a_secure_password
```

### 4. Start Services

```bash
docker-compose up -d
```

This starts:
- **PostgreSQL** on `localhost:5432`
- **Whoopster app** (data sync service)
- **Grafana** on `http://localhost:3000`

**Alternative: Use Pre-Built Images**

Instead of building locally, you can pull pre-built multi-arch images:

```bash
# Pull from GitHub Container Registry
docker pull ghcr.io/yourusername/whoopster:latest

# Update docker-compose.yml to use ghcr.io image
# Then start services
docker-compose up -d
```

Pre-built images are available for:
- `linux/amd64` (Intel/AMD)
- `linux/arm64` (Apple Silicon, Raspberry Pi)

### 5. Authorize Whoop Access

```bash
docker-compose exec app python scripts/init_oauth.py
```

This will:
1. Open your browser to Whoop's authorization page
2. Ask you to grant permissions
3. Store OAuth tokens securely in the database

### 6. View Your Data

1. Open [http://localhost:3000](http://localhost:3000)
2. Login with username `admin` and your `GRAFANA_ADMIN_PASSWORD`
3. Navigate to "Whoop Analytics" dashboard folder
4. The **Whoop Overview** dashboard is automatically loaded with:
   - Sleep performance trends
   - Recovery score gauge
   - Sleep stages breakdown
   - Workout strain analytics
   - HRV trends
   - Heart rate zone distribution

**Manual Dashboard Import** (if needed):
- Go to Dashboards → Import
- Upload `grafana/dashboards/whoop-overview.json`
- Select "Whoopster PostgreSQL" datasource

## Project Structure

```
whoopster/
├── src/                        # Application source code
│   ├── models/                 # SQLAlchemy & Pydantic models
│   │   ├── db_models.py        # Database schema (7 tables)
│   │   └── api_models.py       # API response validation
│   ├── auth/                   # OAuth 2.0 client & token management
│   ├── api/                    # Whoop API client & rate limiting
│   ├── services/               # Data sync services (sleep, recovery, etc.)
│   ├── database/               # Database session & migrations
│   ├── scheduler/              # APScheduler job configuration
│   ├── utils/                  # Logging & utilities
│   ├── config.py               # Application configuration
│   └── main.py                 # Application entry point
│
├── scripts/                    # Utility scripts
│   ├── init_oauth.py           # Interactive OAuth setup
│   └── test_connection.py      # Connection testing
│
├── grafana/                    # Grafana configuration
│   └── provisioning/
│       ├── datasources/        # PostgreSQL datasource
│       └── dashboards/         # Pre-built dashboards
│
├── docker-compose.yml          # Multi-container orchestration
├── Dockerfile                  # Application container
├── requirements.txt            # Python dependencies
├── alembic.ini                 # Database migration config
├── .env.example                # Environment template
├── IMPLEMENTATION.md           # Detailed implementation guide
└── README.md                   # This file
```

## Database Schema

Whoopster stores data in 7 PostgreSQL tables:

| Table | Description | Key Fields |
|-------|-------------|------------|
| `users` | User information | whoop_user_id, email |
| `oauth_tokens` | OAuth access/refresh tokens | access_token, refresh_token, expires_at |
| `sleep_records` | Sleep data | sleep stages, performance, efficiency |
| `recovery_records` | Recovery metrics | recovery_score, hrv_rmssd, resting_heart_rate |
| `workout_records` | Workout activities | strain_score, sport_id, hr_zones |
| `cycle_records` | Physiological cycles | daily_strain, avg_heart_rate |
| `sync_status` | Sync tracking | last_sync_time, records_fetched |

All tables use UUID primary keys matching Whoop's identifiers for natural deduplication.

## Configuration

Configuration is managed via environment variables in `.env`:

```bash
# PostgreSQL
POSTGRES_DB=whoopster
POSTGRES_USER=whoopster
POSTGRES_PASSWORD=your_secure_password

# Whoop API
WHOOP_CLIENT_ID=your_client_id
WHOOP_CLIENT_SECRET=your_client_secret
WHOOP_REDIRECT_URI=http://localhost:8000/callback

# Application
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
SYNC_INTERVAL_MINUTES=15          # How often to fetch new data
ENVIRONMENT=development           # development or production

# Grafana
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=your_secure_password
```

## Usage

### View Logs

```bash
# Follow app logs
docker-compose logs -f app

# View all service logs
docker-compose logs -f
```

### Check Sync Status

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U whoopster -d whoopster

# Query sync status
SELECT data_type, last_sync_time, status, records_fetched
FROM sync_status;
```

### Manual Data Sync

```bash
docker-compose exec app python -c "
from src.services.data_collector import DataCollector
DataCollector().sync_all_data()
"
```

### Database Migrations

```bash
# View current migration version
docker-compose exec app alembic current

# View migration history
docker-compose exec app alembic history

# Create new migration after model changes
docker-compose exec app alembic revision --autogenerate -m "Description"

# Apply migrations
docker-compose exec app alembic upgrade head
```

## Development

### Local Setup

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run locally (requires PostgreSQL running)
export $(cat .env | xargs)
python -m src.main
```

### Run Tests

```bash
pytest tests/ -v --cov=src
```

### Code Quality

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/
```

## Grafana Dashboards

Whoopster includes pre-built dashboards for:

### Sleep Analysis
- Sleep performance trends over time
- Sleep stage distribution (light, deep, REM, awake)
- Sleep consistency metrics
- Respiratory rate tracking

### Recovery Tracking
- Recovery score trends
- HRV (Heart Rate Variability) analysis
- Resting heart rate trends
- Recovery vs strain correlation

### Workout Analytics
- Workout strain by sport type
- Heart rate zone distribution
- Workout frequency calendar heatmap
- Distance and kilojoules burned

### Physiological Cycles
- Daily strain trends
- Average heart rate patterns
- Strain vs recovery relationships

## Current Status

**Version**: 0.1.0 (In Development)
**Progress**: Foundation Complete (27%)

### ✅ Completed
- Project structure and configuration
- Complete database schema (7 tables)
- API response validation models
- Comprehensive documentation

### 🚧 In Progress
- Database migrations (Alembic setup)
- OAuth 2.0 authentication client
- Whoop API client with pagination
- Data sync services

### 📋 Planned
- Docker containerization
- Grafana dashboard provisioning
- Initial data backfill script
- Automated testing suite

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for detailed progress and roadmap.

## Roadmap

### v0.1.0 (Current)
- [x] Database schema design
- [ ] OAuth 2.0 authentication
- [ ] Basic data sync (sleep, recovery, workouts, cycles)
- [ ] Docker Compose deployment
- [ ] Pre-built Grafana dashboards

### v0.2.0 (Future)
- [ ] Multi-user support
- [ ] Data export (CSV, JSON)
- [ ] Custom Grafana alerts
- [ ] Historical data backfill
- [ ] Web UI for OAuth management

### v0.3.0 (Future)
- [ ] Whoop webhooks support (real-time updates)
- [ ] Advanced analytics (correlations, predictions)
- [ ] Mobile-optimized dashboards
- [ ] Data sharing/export API

## Troubleshooting

### OAuth tokens expired
```bash
# Re-run OAuth setup
docker-compose exec app python scripts/init_oauth.py
```

### Sync not running
```bash
# Check app logs for errors
docker-compose logs -f app

# Verify scheduler is running
docker-compose exec app python -c "
from src.scheduler.job_scheduler import WhoopScheduler
print(WhoopScheduler.scheduler.get_jobs())
"
```

### Database connection failed
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
docker-compose exec postgres pg_isready -U whoopster
```

### Missing data in Grafana
```bash
# Check sync_status table
docker-compose exec postgres psql -U whoopster -d whoopster \
  -c "SELECT * FROM sync_status;"

# Verify API credentials
docker-compose exec app python scripts/test_connection.py
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Workflow
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Security

- Never commit `.env` files or credentials
- OAuth tokens are stored encrypted in PostgreSQL
- All API communication uses HTTPS
- Database credentials are configurable via environment variables

To report security vulnerabilities, please email security@example.com.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Whoop](https://www.whoop.com/) for their excellent API and developer program
- [SQLAlchemy](https://www.sqlalchemy.org/) for powerful ORM capabilities
- [Pydantic](https://docs.pydantic.dev/) for data validation
- [Grafana](https://grafana.com/) for beautiful visualizations
- [APScheduler](https://apscheduler.readthedocs.io/) for reliable job scheduling

## Support

- **Documentation**: See [IMPLEMENTATION.md](IMPLEMENTATION.md) for detailed technical documentation
- **Issues**: [GitHub Issues](https://github.com/yourusername/whoopster/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/whoopster/discussions)
- **Whoop API**: [developer.whoop.com](https://developer.whoop.com/)

---

**Made with ❤️ by athletes, for athletes**

*Whoopster is not affiliated with or endorsed by Whoop. All product names, logos, and brands are property of their respective owners.*
