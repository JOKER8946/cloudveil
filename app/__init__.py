"""CloudVeil application factory.

Creates and configures the Flask app, registers extensions, blueprints, CLI
commands, security headers and the reverse-proxy fix. Keep this module
import-light: it must succeed even when external Azure services or the database
are unreachable (the health endpoint reports status).
"""

from __future__ import annotations

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import get_config
from .extensions import db, limiter, migrate


def create_app(config_name: str | None = None) -> Flask:
    """Build a configured Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    # App Service terminates TLS and forwards via a reverse proxy; trust one hop
    # so request.remote_addr / scheme reflect the real client.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    _init_extensions(app)
    _register_blueprints(app)
    _register_cli(app)
    _register_security_headers(app)

    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    # Import models so Flask-Migrate autogenerate and create_all see them.
    from . import models  # noqa: F401


def _register_blueprints(app: Flask) -> None:
    from .admin.routes import bp as admin_bp
    from .auth.routes import bp as auth_bp
    from .files.routes import bp as files_bp
    from .health.routes import bp as health_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(admin_bp)


def _register_cli(app: Flask) -> None:
    from .cli import register_cli

    register_cli(app)


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'",
        )
        if app.config.get("SESSION_COOKIE_SECURE", True):
            resp.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return resp
