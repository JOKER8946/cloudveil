"""Application configuration, read entirely from environment variables.

No resource names, URLs, or secrets are hard-coded. Each config class is
selected by ``create_app(config_name)`` in :mod:`app`.
"""

from __future__ import annotations

import os
from urllib.parse import quote_plus


def _bool(name: str, default: bool = False) -> bool:
    """Read a boolean-ish environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _mysql_uri() -> str:
    """Build the MySQL connection string from discrete env vars.

    Returns an empty string if the database is not configured yet so the app
    can still boot (the health check reports the database as unavailable).
    """
    host = os.environ.get("MYSQL_HOST", "")
    user = os.environ.get("MYSQL_USER", "")
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "cloudveil")
    port = os.environ.get("MYSQL_PORT", "3306")
    ssl_ca = os.environ.get("MYSQL_SSL_CA", "")
    if not (host and user and password):
        return ""
    # URL-encode credentials: the password may contain characters such as '@'
    # or ':' that would otherwise break URL parsing.
    user_q = quote_plus(user)
    password_q = quote_plus(password)
    uri = (
        f"mysql+pymysql://{user_q}:{password_q}@{host}:{port}/{database}"
        "?charset=utf8mb4"
    )
    if ssl_ca:
        uri += f"&ssl_ca={quote_plus(ssl_ca)}"
    return uri


class BaseConfig:
    """Settings shared by every environment."""

    # Flask core
    SECRET_KEY = os.environ.get("JWT_SECRET", "dev-insecure-change-me")
    JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-change-me")
    JWT_EXPIRY_MINUTES = int(os.environ.get("JWT_EXPIRY_MINUTES", "30"))

    # Uploads
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Azure service endpoints (populated in App Service settings)
    KEYVAULT_URL = os.environ.get("KEYVAULT_URL", "")
    KEK_NAME = os.environ.get("KEK_NAME", "cloudveil-kek")
    STORAGE_ACCOUNT_URL = os.environ.get("STORAGE_ACCOUNT_URL", "")
    STORAGE_CONTAINER = os.environ.get("STORAGE_CONTAINER", "encrypted-files")
    PRIMARY_REGION = os.environ.get("PRIMARY_REGION", "")

    # Telemetry
    APPLICATIONINSIGHTS_CONNECTION_STRING = os.environ.get(
        "APPLICATIONINSIGHTS_CONNECTION_STRING", ""
    )

    # Cookies / security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Strict"


class ProdConfig(BaseConfig):
    """Live Azure App Service configuration (MySQL over TLS)."""

    DEBUG = False
    TESTING = False

    SQLALCHEMY_DATABASE_URI = _mysql_uri()


class TestConfig(BaseConfig):
    """CI / unit-test configuration — SQLite in-memory, no external services."""

    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_COOKIE_SECURE = False  # tests use HTTP
    JWT_SECRET = "test-secret"
    SECRET_KEY = "test-secret"
    RATELIMIT_ENABLED = False


_CONFIGS = {
    "prod": ProdConfig,
    "production": ProdConfig,
    "test": TestConfig,
    "testing": TestConfig,
}


def get_config(name: str | None = None):
    """Resolve a config class by name, defaulting to the ``FLASK_CONFIG`` env."""
    key = (name or os.environ.get("FLASK_CONFIG") or "prod").lower()
    return _CONFIGS.get(key, ProdConfig)
