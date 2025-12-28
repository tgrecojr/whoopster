"""Application configuration using Pydantic Settings."""

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationError
from dotenv import load_dotenv

# Load .env file from project root (parent of src directory)
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load .env file explicitly using python-dotenv if it exists
# This ensures the file is loaded regardless of current working directory
# In Docker/production, environment variables can be passed directly without a .env file
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL Configuration
    postgres_db: str = "whoopster"
    postgres_user: str = "whoopster"
    postgres_password: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        """
        Construct PostgreSQL connection URL with URL-encoded credentials.

        This ensures special characters in passwords are properly encoded.
        """
        # URL-encode username and password to handle special characters
        encoded_user = quote_plus(self.postgres_user)
        encoded_password = quote_plus(self.postgres_password)

        return (
            f"postgresql://{encoded_user}:{encoded_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Whoop API Configuration
    whoop_client_id: str
    whoop_client_secret: str
    whoop_redirect_uri: str = "http://localhost:8000/callback"
    whoop_api_base_url: str = "https://api.prod.whoop.com"
    whoop_auth_url: str = "https://api.prod.whoop.com/oauth/oauth2/auth"
    whoop_token_url: str = "https://api.prod.whoop.com/oauth/oauth2/token"

    # Application Configuration
    log_level: str = "INFO"
    sync_interval_minutes: int = 15
    environment: str = "development"

    # Rate Limiting
    max_requests_per_minute: int = 60

    # Grafana Configuration
    grafana_admin_user: str = "admin"
    grafana_admin_password: str

    # Security Configuration
    token_encryption_key: str  # Required: Fernet encryption key for OAuth tokens

    # Pydantic Settings Configuration
    # Note: .env is loaded via python-dotenv above for better path resolution
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )


# Singleton instance with user-friendly error handling
def _initialize_settings() -> Settings:
    """
    Initialize settings with helpful error messages for missing required fields.

    Returns:
        Settings: Initialized settings object

    Raises:
        SystemExit: If required environment variables are missing
    """
    try:
        return Settings()
    except ValidationError as e:
        # Extract missing required fields
        missing_fields = []
        invalid_fields = []

        for error in e.errors():
            field_name = error['loc'][0] if error['loc'] else 'unknown'
            error_type = error['type']

            if error_type == 'missing':
                # Convert snake_case to UPPER_CASE for environment variable name
                env_var_name = str(field_name).upper()
                missing_fields.append(env_var_name)
            else:
                invalid_fields.append({
                    'field': str(field_name).upper(),
                    'error': error['msg']
                })

        # Build user-friendly error message
        error_lines = [
            "\n" + "="*70,
            "CONFIGURATION ERROR: Missing or invalid environment variables",
            "="*70,
        ]

        if missing_fields:
            error_lines.append("\nMissing required environment variables:")
            for field in missing_fields:
                error_lines.append(f"  - {field}")

        if invalid_fields:
            error_lines.append("\nInvalid environment variables:")
            for item in invalid_fields:
                error_lines.append(f"  - {item['field']}: {item['error']}")

        error_lines.extend([
            f"\nPlease set these environment variables in your .env file or Docker environment.",
            f"For local development, create .env at: {ENV_FILE}",
            f"You can use .env.example as a template: {PROJECT_ROOT / '.env.example'}",
            "",
            "For Docker/production, pass these as environment variables via:",
            "  - docker-compose.yml (environment section)",
            "  - docker run -e VARIABLE=value",
            "  - Kubernetes secrets/configmaps",
            "",
            "For TOKEN_ENCRYPTION_KEY, generate a new key with:",
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"",
            "="*70 + "\n",
        ])

        print("\n".join(error_lines), file=sys.stderr)
        sys.exit(1)


settings = _initialize_settings()
