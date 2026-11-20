"""Gunicorn entry point: ``gunicorn wsgi:app``.

Telemetry is configured here (the serving process) rather than in the app
factory, so ``flask`` CLI commands (migrations, create-admin, seed-demo) do not
initialise OpenTelemetry — doing so breaks Flask's app loading.
"""

from app import configure_telemetry, create_app

app = create_app("prod")
configure_telemetry(app)
