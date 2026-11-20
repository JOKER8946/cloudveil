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


@click.command("rewrap-keys")
@with_appcontext
def rewrap_keys():
    """Re-wrap every file's DEK with the newest KEK version (blobs untouched)."""
    from .models import File
    from .providers import get_key_provider

    provider = get_key_provider()
    files = File.query.filter_by(is_deleted=False).all()
    count = 0
    for record in files:
        dek = provider.unwrap(bytes(record.wrapped_key), record.kek_key_id)
        new_wrapped, new_kid = provider.wrap(dek)
        del dek
        record.wrapped_key = new_wrapped
        record.kek_key_id = new_kid
        count += 1
    db.session.commit()
    click.echo(f"Re-wrapped {count} file key(s) with the latest KEK version.")


def register_cli(app) -> None:
    app.cli.add_command(create_admin)
    app.cli.add_command(rewrap_keys)
