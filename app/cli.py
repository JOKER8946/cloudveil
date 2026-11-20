"""Flask CLI commands.

``create-admin`` is run on startup (idempotent). ``seed-demo`` and
``rewrap-keys`` are implemented in later phases.
"""

from __future__ import annotations

import os

import click
from flask.cli import with_appcontext

from .auth.service import create_user
from .extensions import db
from .models import User


@click.command("create-admin")
@with_appcontext
def create_admin():
    """Create (or promote) the seed admin from SEED_ADMIN_* env vars."""
    email = (os.environ.get("SEED_ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("SEED_ADMIN_PASSWORD") or ""
    if not email or not password:
        click.echo("SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD not set; skipping.")
        return

    existing = User.query.filter_by(email=email).first()
    if existing is not None:
        if existing.role != "admin":
            existing.role = "admin"
            db.session.commit()
            click.echo(f"Promoted existing user to admin: {email}")
        else:
            click.echo(f"Admin already exists: {email}")
        return

    user = create_user("CloudVeil Admin", email, password, role="admin")
    click.echo(f"Created admin: {user.email}")


def register_cli(app) -> None:
    app.cli.add_command(create_admin)
