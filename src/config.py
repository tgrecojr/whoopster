"""Application configuration using Pydantic Settings."""

from urllib.parse import quote_plus
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton instance
settings = Settings()
