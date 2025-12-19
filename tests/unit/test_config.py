"""Tests for configuration module."""

import pytest
from urllib.parse import quote_plus

from src.config import Settings


@pytest.mark.unit
class TestSettings:
    """Tests for Settings class."""

    def test_settings_loads_from_env(self, monkeypatch):
        """Test that settings load from environment variables."""
        monkeypatch.setenv("POSTGRES_DB", "test_db")
        monkeypatch.setenv("POSTGRES_USER", "test_user")
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
        monkeypatch.setenv("POSTGRES_HOST", "test_host")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")

        settings = Settings()

        assert settings.postgres_db == "test_db"
        assert settings.postgres_user == "test_user"
        assert settings.postgres_password == "test_password"
        assert settings.postgres_host == "test_host"
        assert settings.postgres_port == 5433
        assert settings.whoop_client_id == "test_client_id"
        assert settings.whoop_client_secret == "test_client_secret"

    def test_settings_has_defaults(self, monkeypatch, tmp_path):
        """Test that settings have default values when no .env file exists."""
        # Clear environment variables set by pytest-env to test actual defaults
        monkeypatch.delenv("POSTGRES_DB", raising=False)
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)

        # Set only required environment variables
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        # Change to a temporary directory where no .env file exists
        monkeypatch.chdir(tmp_path)

        settings = Settings()

        assert settings.postgres_db == "whoopster"
        assert settings.postgres_user == "whoopster"
        assert settings.postgres_host == "postgres"
        assert settings.postgres_port == 5432
        assert settings.log_level == "INFO"
        assert settings.sync_interval_minutes == 15
        assert settings.environment == "development"
        assert settings.max_requests_per_minute == 60

    def test_database_url_construction(self, monkeypatch):
        """Test that database URL is constructed correctly."""
        monkeypatch.setenv("POSTGRES_DB", "test_db")
        monkeypatch.setenv("POSTGRES_USER", "test_user")
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
        monkeypatch.setenv("POSTGRES_HOST", "localhost")
        monkeypatch.setenv("POSTGRES_PORT", "5432")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        settings = Settings()

        expected_url = "postgresql://test_user:test_password@localhost:5432/test_db"
        assert settings.database_url == expected_url

    def test_database_url_with_special_characters(self, monkeypatch):
        """Test that database URL handles special characters in password."""
        monkeypatch.setenv("POSTGRES_DB", "test_db")
        monkeypatch.setenv("POSTGRES_USER", "test_user")
        monkeypatch.setenv("POSTGRES_PASSWORD", "pass@word#123%")
        monkeypatch.setenv("POSTGRES_HOST", "localhost")
        monkeypatch.setenv("POSTGRES_PORT", "5432")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        settings = Settings()

        encoded_password = quote_plus("pass@word#123%")
        expected_url = f"postgresql://test_user:{encoded_password}@localhost:5432/test_db"
        assert settings.database_url == expected_url

    def test_database_url_encodes_username(self, monkeypatch):
        """Test that database URL encodes username with special characters."""
        monkeypatch.setenv("POSTGRES_DB", "test_db")
        monkeypatch.setenv("POSTGRES_USER", "user@domain")
        monkeypatch.setenv("POSTGRES_PASSWORD", "password")
        monkeypatch.setenv("POSTGRES_HOST", "localhost")
        monkeypatch.setenv("POSTGRES_PORT", "5432")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        settings = Settings()

        encoded_user = quote_plus("user@domain")
        expected_url = f"postgresql://{encoded_user}:password@localhost:5432/test_db"
        assert settings.database_url == expected_url

    def test_whoop_api_urls(self, monkeypatch):
        """Test Whoop API URL configuration."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        settings = Settings()

        assert settings.whoop_api_base_url == "https://api.prod.whoop.com"
        assert settings.whoop_auth_url == "https://api.prod.whoop.com/oauth/oauth2/auth"
        assert settings.whoop_token_url == "https://api.prod.whoop.com/oauth/oauth2/token"
        assert settings.whoop_redirect_uri == "http://localhost:8000/callback"

    def test_custom_whoop_urls(self, monkeypatch):
        """Test custom Whoop API URL configuration."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("WHOOP_API_BASE_URL", "https://custom.api.com")
        monkeypatch.setenv("WHOOP_REDIRECT_URI", "https://custom.redirect.com/callback")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        settings = Settings()

        assert settings.whoop_api_base_url == "https://custom.api.com"
        assert settings.whoop_redirect_uri == "https://custom.redirect.com/callback"

    def test_sync_interval_custom(self, monkeypatch):
        """Test custom sync interval."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("SYNC_INTERVAL_MINUTES", "30")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        settings = Settings()

        assert settings.sync_interval_minutes == 30

    def test_log_level_custom(self, monkeypatch):
        """Test custom log level."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        settings = Settings()

        assert settings.log_level == "DEBUG"

    def test_environment_custom(self, monkeypatch):
        """Test custom environment."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
        monkeypatch.setenv("WHOOP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "test_grafana_password")

        settings = Settings()

        assert settings.environment == "production"
