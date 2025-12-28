# Whoopster Deployment Guide

## Overview

This guide covers deploying Whoopster to production environments using Docker Compose. For development setup, see the main [README](../README.md).

## Prerequisites

### System Requirements

**Minimum:**
- 2 CPU cores
- 4 GB RAM
- 20 GB disk space
- Linux (Ubuntu 20.04+ recommended) or macOS

**Recommended:**
- 4 CPU cores
- 8 GB RAM
- 50 GB SSD storage
- Ubuntu 22.04 LTS

### Required Software

```bash
# Docker
docker --version  # 24.0+
docker-compose --version  # 2.20+

# Git
git --version  # 2.30+

# Optional: PostgreSQL client for debugging
psql --version  # 15+
```

### Install Docker

**Ubuntu:**
```bash
# Update package index
sudo apt-get update

# Install dependencies
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in for group change to take effect
```

**macOS:**
```bash
# Install Docker Desktop
brew install --cask docker

# Or download from: https://www.docker.com/products/docker-desktop
```

## Initial Setup

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/whoopster.git
cd whoopster
```

### 2. Create Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` with production values:

```bash
# PostgreSQL Configuration
POSTGRES_DB=whoopster
POSTGRES_USER=whoopster
POSTGRES_PASSWORD=<STRONG_PASSWORD_HERE>  # Generate with: openssl rand -base64 32
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Whoop API Configuration
# Get these from: https://developer.whoop.com
WHOOP_CLIENT_ID=<YOUR_CLIENT_ID>
WHOOP_CLIENT_SECRET=<YOUR_CLIENT_SECRET>
WHOOP_REDIRECT_URI=http://localhost:8000/callback  # Update for production

# Application Configuration
LOG_LEVEL=INFO  # Use INFO or WARNING in production
SYNC_INTERVAL_MINUTES=15
ENVIRONMENT=production

# Grafana Configuration
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<STRONG_PASSWORD_HERE>  # Generate with: openssl rand -base64 32
```

**Security Notes:**
- Never commit `.env` to version control
- Use strong, unique passwords (32+ characters)
- Rotate credentials periodically
- Consider using secrets management (AWS Secrets Manager, HashiCorp Vault)

### 3. Generate Secrets

```bash
# Generate PostgreSQL password
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)" >> .env

# Generate Grafana password
echo "GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 32)" >> .env
```

### 4. Configure Whoop OAuth

1. Visit [Whoop Developer Portal](https://developer.whoop.com)
2. Create a new application
3. Configure redirect URI:
   - Development: `http://localhost:8000/callback`
   - Production: `https://yourdomain.com/callback`
4. Copy Client ID and Client Secret to `.env`
5. Request scopes: `read:sleep`, `read:recovery`, `read:workout`, `read:cycles`

## Deployment Options

### Option 1: Docker Compose (Recommended)

#### Production docker-compose.yml

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: whoopster-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"  # Only bind to localhost
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - whoopster-network

  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: whoopster-app
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      WHOOP_CLIENT_ID: ${WHOOP_CLIENT_ID}
      WHOOP_CLIENT_SECRET: ${WHOOP_CLIENT_SECRET}
      WHOOP_REDIRECT_URI: ${WHOOP_REDIRECT_URI}
      LOG_LEVEL: ${LOG_LEVEL}
      SYNC_INTERVAL_MINUTES: ${SYNC_INTERVAL_MINUTES}
      ENVIRONMENT: production
    volumes:
      - app_logs:/app/logs
    networks:
      - whoopster-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  grafana:
    image: grafana/grafana:10.2.0
    container_name: whoopster-grafana
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_INSTALL_PLUGINS: ""
      GF_SERVER_ROOT_URL: "https://yourdomain.com"  # Update for production
      GF_SERVER_SERVE_FROM_SUB_PATH: "false"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    ports:
      - "127.0.0.1:3000:3000"  # Only bind to localhost
    networks:
      - whoopster-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  postgres_data:
    driver: local
  grafana_data:
    driver: local
  app_logs:
    driver: local

networks:
  whoopster-network:
    driver: bridge
```

#### Deploy

```bash
# Build and start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Check status
docker-compose -f docker-compose.prod.yml ps
```

### Option 2: Kubernetes

See [kubernetes/](../kubernetes/) directory for Kubernetes manifests (not yet implemented).

### Option 3: Manual Installation

For deployments without Docker:

```bash
# Install Python 3.11+
sudo apt-get install python3.11 python3.11-venv

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up PostgreSQL
sudo apt-get install postgresql-15
sudo -u postgres createdb whoopster
sudo -u postgres createuser whoopster

# Run migrations
alembic upgrade head

# Start application
python -m src.main
```

## Post-Deployment Steps

### 1. Run OAuth Setup

```bash
# Connect to running container
docker-compose -f docker-compose.prod.yml exec app python scripts/init_oauth.py

# Follow prompts to authorize Whoop access
# This only needs to be done once per user
```

### 2. Verify Database

```bash
# Connect to PostgreSQL
docker-compose -f docker-compose.prod.yml exec postgres psql -U whoopster -d whoopster

# Check tables
\dt

# Verify user exists
SELECT * FROM users;

# Check OAuth token
SELECT user_id, expires_at, scopes FROM oauth_tokens;

# Exit
\q
```

### 3. Verify Scheduler

```bash
# Check app logs for scheduler initialization
docker-compose -f docker-compose.prod.yml logs app | grep -i scheduler

# Should see:
# Scheduler initialized
# Added sync jobs for all users
# Scheduler started
```

### 4. Access Grafana

```bash
# Get Grafana URL
echo "http://localhost:3000"

# Or if using reverse proxy:
echo "https://yourdomain.com"

# Login with credentials from .env
# Username: ${GRAFANA_ADMIN_USER}
# Password: ${GRAFANA_ADMIN_PASSWORD}
```

## Reverse Proxy Setup (Production)

### Nginx Configuration

Create `/etc/nginx/sites-available/whoopster`:

```nginx
upstream grafana {
    server 127.0.0.1:3000;
}

server {
    listen 80;
    server_name yourdomain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Grafana Proxy
    location / {
        proxy_pass http://grafana;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Logging
    access_log /var/log/nginx/whoopster-access.log;
    error_log /var/log/nginx/whoopster-error.log;
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/whoopster /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal is configured by default
# Test renewal
sudo certbot renew --dry-run
```

## Monitoring and Logging

### Application Logs

```bash
# View app logs
docker-compose -f docker-compose.prod.yml logs -f app

# Filter for errors
docker-compose -f docker-compose.prod.yml logs app | grep ERROR

# Sync job logs
docker-compose -f docker-compose.prod.yml logs app | grep "Sync completed"

# View log files directly
docker-compose -f docker-compose.prod.yml exec app ls -lh /app/logs
docker-compose -f docker-compose.prod.yml exec app tail -f /app/logs/whoopster.log
```

### PostgreSQL Logs

```bash
# View database logs
docker-compose -f docker-compose.prod.yml logs -f postgres

# Check slow queries (if logging enabled)
docker-compose -f docker-compose.prod.yml exec postgres cat /var/lib/postgresql/data/log/postgresql.log
```

### Grafana Logs

```bash
# View Grafana logs
docker-compose -f docker-compose.prod.yml logs -f grafana
```

### Log Aggregation

For production, consider centralized logging:

**Option 1: ELK Stack (Elasticsearch, Logstash, Kibana)**

```yaml
# Add to docker-compose.prod.yml
services:
  app:
    logging:
      driver: "gelf"
      options:
        gelf-address: "udp://logstash:12201"
        tag: "whoopster-app"
```

**Option 2: Loki + Grafana**

```yaml
services:
  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  app:
    logging:
      driver: "loki"
      options:
        loki-url: "http://loki:3100/loki/api/v1/push"
```

**Option 3: CloudWatch Logs (AWS)**

```yaml
services:
  app:
    logging:
      driver: "awslogs"
      options:
        awslogs-region: "us-east-1"
        awslogs-group: "whoopster"
        awslogs-stream: "app"
```

## Backup and Recovery

### Database Backups

**Manual Backup:**
```bash
# Create backup
docker-compose -f docker-compose.prod.yml exec postgres pg_dump -U whoopster whoopster > backup_$(date +%Y%m%d_%H%M%S).sql

# Compress backup
gzip backup_*.sql
```

**Automated Backups:**

Create `scripts/backup.sh`:

```bash
#!/bin/bash
set -e

BACKUP_DIR="/backups/whoopster"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/whoopster_$TIMESTAMP.sql.gz"
RETENTION_DAYS=30

# Create backup directory
mkdir -p $BACKUP_DIR

# Perform backup
docker-compose -f docker-compose.prod.yml exec -T postgres \
    pg_dump -U whoopster whoopster | gzip > $BACKUP_FILE

# Delete old backups
find $BACKUP_DIR -name "whoopster_*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $BACKUP_FILE"
```

**Schedule with cron:**
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/whoopster/scripts/backup.sh >> /var/log/whoopster-backup.log 2>&1
```

**Restore from Backup:**
```bash
# Stop app to avoid conflicts
docker-compose -f docker-compose.prod.yml stop app

# Restore database
gunzip -c backup_20250101_020000.sql.gz | \
    docker-compose -f docker-compose.prod.yml exec -T postgres \
    psql -U whoopster -d whoopster

# Restart app
docker-compose -f docker-compose.prod.yml start app
```

### Configuration Backups

```bash
# Backup environment configuration
cp .env .env.backup_$(date +%Y%m%d)

# Backup Grafana dashboards
docker-compose -f docker-compose.prod.yml exec grafana \
    grafana-cli admin export-dashboards /tmp/dashboards
docker cp whoopster-grafana:/tmp/dashboards ./grafana_backup_$(date +%Y%m%d)
```

### Disaster Recovery

**Complete System Recovery:**

1. **Restore code:**
   ```bash
   git clone https://github.com/yourusername/whoopster.git
   cd whoopster
   ```

2. **Restore configuration:**
   ```bash
   cp .env.backup .env
   ```

3. **Start services:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d postgres
   ```

4. **Restore database:**
   ```bash
   gunzip -c latest_backup.sql.gz | \
       docker-compose -f docker-compose.prod.yml exec -T postgres \
       psql -U whoopster -d whoopster
   ```

5. **Start application:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

6. **Verify:**
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   docker-compose -f docker-compose.prod.yml logs -f
   ```

## Scaling

### Vertical Scaling

**Increase container resources:**

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

  postgres:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
```

### Horizontal Scaling

For multiple users or higher sync frequency:

**Database Connection Pooling:**

```python
# src/config.py
class Settings(BaseSettings):
    # ...
    db_pool_size: int = 20
    db_max_overflow: int = 40
```

**Multiple App Instances:**

```yaml
services:
  app:
    deploy:
      replicas: 3  # Run 3 app instances
```

**Load Balancer:**

Use nginx to distribute requests:

```nginx
upstream whoopster_app {
    least_conn;
    server app1:8000;
    server app2:8000;
    server app3:8000;
}
```

### Database Optimization

**Enable Query Logging:**

```sql
-- Monitor slow queries
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries > 1s
SELECT pg_reload_conf();

-- View slow queries
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

**Optimize Indexes:**

```sql
-- Check missing indexes
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE tablename IN ('sleep_records', 'recovery_records', 'workout_records', 'cycle_records')
ORDER BY abs(correlation) DESC;

-- Create additional indexes if needed
CREATE INDEX idx_sleep_performance ON sleep_records(sleep_performance_percentage);
CREATE INDEX idx_recovery_score ON recovery_records(recovery_score);
```

**Vacuum and Analyze:**

```bash
# Manual vacuum
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "VACUUM ANALYZE;"

# Enable autovacuum (enabled by default)
ALTER SYSTEM SET autovacuum = on;
```

## Security Hardening

### Docker Security

**1. Use Non-Root User:**

Update Dockerfile:

```dockerfile
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r whoopster && useradd -r -g whoopster whoopster

# Set ownership
WORKDIR /app
COPY --chown=whoopster:whoopster . .

# Switch to non-root user
USER whoopster

CMD ["python", "-m", "src.main"]
```

**2. Scan Images:**

```bash
# Install Trivy
sudo apt-get install trivy

# Scan image
trivy image whoopster-app:latest
```

**3. Limit Capabilities:**

```yaml
services:
  app:
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    security_opt:
      - no-new-privileges:true
```

### Network Security

**1. Firewall Rules:**

```bash
# Allow only necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**2. Docker Network Isolation:**

```yaml
networks:
  whoopster-network:
    driver: bridge
    internal: true  # No external access

  public-network:
    driver: bridge
```

**3. Database Security:**

```sql
-- Restrict database user permissions
REVOKE ALL ON DATABASE whoopster FROM PUBLIC;
GRANT CONNECT ON DATABASE whoopster TO whoopster;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO whoopster;

-- Read-only user for Grafana
CREATE USER grafana_readonly WITH PASSWORD 'strong_password';
GRANT CONNECT ON DATABASE whoopster TO grafana_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_readonly;
```

### Application Security

**1. Token Encryption:**

Implement application-level encryption for OAuth tokens:

```python
# src/auth/encryption.py
from cryptography.fernet import Fernet
import os

class TokenEncryption:
    def __init__(self):
        key = os.getenv("ENCRYPTION_KEY")  # Store in .env
        self.cipher = Fernet(key.encode())

    def encrypt(self, token: str) -> str:
        return self.cipher.encrypt(token.encode()).decode()

    def decrypt(self, encrypted_token: str) -> str:
        return self.cipher.decrypt(encrypted_token.encode()).decode()
```

**2. Secrets Management:**

Use external secrets manager in production:

```bash
# AWS Secrets Manager
aws secretsmanager get-secret-value --secret-id whoopster/postgres-password

# HashiCorp Vault
vault kv get secret/whoopster/postgres-password
```

**3. Rate Limiting:**

Already implemented in `src/api/rate_limiter.py`. Adjust for production:

```python
# src/config.py
class Settings(BaseSettings):
    # ...
    api_rate_limit: int = 54  # 90% of Whoop's 60 req/min limit
    rate_limit_window: int = 60  # seconds
```

## Health Checks

### Application Health Endpoint

Create `src/api/health.py`:

```python
from fastapi import FastAPI
from src.database.session import engine
from src.auth.token_manager import TokenManager

app = FastAPI()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health = {
        "status": "healthy",
        "checks": {}
    }

    # Database check
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        health["checks"]["database"] = "healthy"
    except Exception as e:
        health["status"] = "unhealthy"
        health["checks"]["database"] = f"unhealthy: {str(e)}"

    # Token check
    try:
        token_manager = TokenManager(user_id=1)
        token = await token_manager.get_valid_token()
        health["checks"]["auth"] = "healthy"
    except Exception as e:
        health["checks"]["auth"] = f"warning: {str(e)}"

    return health
```

### Docker Health Checks

```yaml
services:
  app:
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## Troubleshooting Production Issues

### Container Won't Start

```bash
# Check container status
docker-compose -f docker-compose.prod.yml ps

# View detailed logs
docker-compose -f docker-compose.prod.yml logs app

# Check for port conflicts
sudo lsof -i :3000
sudo lsof -i :5432

# Restart services
docker-compose -f docker-compose.prod.yml restart
```

### Database Connection Errors

```bash
# Verify PostgreSQL is running
docker-compose -f docker-compose.prod.yml exec postgres pg_isready

# Check database credentials
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "SELECT 1"

# View connection logs
docker-compose -f docker-compose.prod.yml logs postgres | grep -i connection
```

### Sync Jobs Not Running

```bash
# Check scheduler logs
docker-compose -f docker-compose.prod.yml logs app | grep -i scheduler

# Verify jobs in database
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "SELECT * FROM apscheduler_jobs;"

# Check sync status
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "SELECT * FROM sync_status ORDER BY last_sync_time DESC;"
```

### High Memory Usage

```bash
# Check container resource usage
docker stats

# Check database size
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "
        SELECT pg_size_pretty(pg_database_size('whoopster')) as db_size;
    "

# Check table sizes
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "
        SELECT
            tablename,
            pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(tablename::regclass) DESC;
    "
```

### Token Expired Issues

```bash
# Check token expiration
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "
        SELECT user_id, expires_at, expires_at < NOW() as is_expired
        FROM oauth_tokens;
    "

# Manually refresh token
docker-compose -f docker-compose.prod.yml exec app python scripts/init_oauth.py
```

## Maintenance

### Update Application

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

# Run migrations
docker-compose -f docker-compose.prod.yml exec app alembic upgrade head
```

### Database Maintenance

```bash
# Vacuum and analyze
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "VACUUM ANALYZE;"

# Reindex
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "REINDEX DATABASE whoopster;"

# Check for bloat
docker-compose -f docker-compose.prod.yml exec postgres \
    psql -U whoopster -d whoopster -c "
        SELECT
            schemaname,
            tablename,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
            ROUND(100 * pg_total_relation_size(schemaname||'.'||tablename) / pg_database_size(current_database())) AS percent
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
    "
```

### Log Rotation

Docker handles log rotation automatically with the configuration in docker-compose.yml:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

For system logs, configure logrotate:

```bash
# Create /etc/logrotate.d/whoopster
/var/log/whoopster/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 whoopster whoopster
    sharedscripts
    postrotate
        docker-compose -f /path/to/docker-compose.prod.yml restart app
    endscript
}
```

## Performance Monitoring

### Prometheus + Grafana

Add Prometheus for metrics collection:

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - whoopster-network

volumes:
  prometheus_data:
```

**prometheus.yml:**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'whoopster'
    static_configs:
      - targets: ['app:8000']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres_exporter:9187']
```

### Database Monitoring

Install postgres_exporter:

```yaml
services:
  postgres_exporter:
    image: prometheuscommunity/postgres-exporter
    environment:
      DATA_SOURCE_NAME: "postgresql://whoopster:${POSTGRES_PASSWORD}@postgres:5432/whoopster?sslmode=disable"
    ports:
      - "9187:9187"
    networks:
      - whoopster-network
```

## Cost Optimization

### Resource Optimization

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 1G
```

### Data Retention Policy

Implement data retention to manage storage:

```python
# src/services/data_retention.py
from datetime import datetime, timedelta
from src.database.session import get_db_context
from src.models.db_models import SleepRecord, RecoveryRecord

def cleanup_old_records(days_to_keep: int = 365):
    """Delete records older than specified days."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    with get_db_context() as db:
        # Delete old sleep records
        deleted_sleep = db.query(SleepRecord).filter(
            SleepRecord.start_time < cutoff_date
        ).delete()

        # Similar for other record types
        # ...

        db.commit()

    return {
        "deleted_sleep": deleted_sleep,
        # ...
    }
```

### Scheduled Cleanup

```bash
# Add to crontab - run monthly
0 3 1 * * docker-compose -f /path/to/docker-compose.prod.yml exec app python -c "from src.services.data_retention import cleanup_old_records; cleanup_old_records(365)"
```

## Compliance and Auditing

### Audit Logging

Track important operations:

```python
# src/utils/audit_log.py
import logging
from datetime import datetime

audit_logger = logging.getLogger('audit')

def log_oauth_authorization(user_id: int):
    audit_logger.info(
        "OAuth authorization",
        extra={
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "oauth_authorize"
        }
    )

def log_data_sync(user_id: int, data_type: str, records_synced: int):
    audit_logger.info(
        "Data sync",
        extra={
            "user_id": user_id,
            "data_type": data_type,
            "records_synced": records_synced,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "data_sync"
        }
    )
```

### GDPR Compliance

For European users, implement data export and deletion:

```python
# src/services/gdpr.py
def export_user_data(user_id: int) -> dict:
    """Export all user data (GDPR Article 15)."""
    with get_db_context() as db:
        user = db.query(User).filter_by(id=user_id).first()
        sleep_records = db.query(SleepRecord).filter_by(user_id=user_id).all()
        # ... export all data types

        return {
            "user": user.to_dict(),
            "sleep_records": [r.to_dict() for r in sleep_records],
            # ...
        }

def delete_user_data(user_id: int) -> bool:
    """Delete all user data (GDPR Article 17)."""
    with get_db_context() as db:
        db.query(SleepRecord).filter_by(user_id=user_id).delete()
        db.query(RecoveryRecord).filter_by(user_id=user_id).delete()
        db.query(WorkoutRecord).filter_by(user_id=user_id).delete()
        db.query(CycleRecord).filter_by(user_id=user_id).delete()
        db.query(OAuthToken).filter_by(user_id=user_id).delete()
        db.query(User).filter_by(id=user_id).delete()
        db.commit()

    return True
```

## Support and Documentation

### Internal Documentation

Maintain runbook for common operations:

```markdown
# Whoopster Runbook

## Daily Checks
- [ ] Verify sync jobs running: `docker-compose logs app | grep "Sync completed"`
- [ ] Check error logs: `docker-compose logs app | grep ERROR`
- [ ] Monitor disk usage: `df -h`

## Weekly Checks
- [ ] Review database size
- [ ] Check backup success
- [ ] Review Grafana dashboards

## Monthly Checks
- [ ] Rotate credentials
- [ ] Review and archive old logs
- [ ] Update dependencies
```

### Contact Information

For Whoop API issues:
- Developer Portal: https://developer.whoop.com
- Support: support@whoop.com

For technical support:
- GitHub Issues: https://github.com/yourusername/whoopster/issues
- Documentation: https://github.com/yourusername/whoopster/wiki

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Let's Encrypt](https://letsencrypt.org/)
- [Whoop API Docs](https://developer.whoop.com/docs)
