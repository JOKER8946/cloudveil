"""CloudVeil application factory.

Creates and configures the Flask app, registers extensions and blueprints.
Keep this module import-light: it must succeed even when external Azure
services or the database are unreachable (the health endpoint reports status).
"""

from __future__ import annotations

from flask import Flask

from .config import get_config
from .extensions import db, limiter, migrate


def create_app(config_name: str | None = None) -> Flask:
    """Build a configured Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    _init_extensions(app)
    _register_blueprints(app)

    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)


def _register_blueprints(app: Flask) -> None:
    from .health.routes import bp as health_bp

    app.register_blueprint(health_bp)
