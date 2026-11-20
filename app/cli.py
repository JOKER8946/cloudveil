"""Flask CLI commands: create-admin, seed-demo, rewrap-keys."""

from __future__ import annotations

import os

import click
from flask.cli import with_appcontext

from .auth.service import create_user
from .extensions import db
from .models import User

# A minimal but valid PDF (starts with the %PDF magic) used for demo documents.
_DEMO_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)

# Fake demo population (NEVER real personal data) — an admissions use case.
_DEMO_STUDENTS = [
    ("Asha Rao", "asha.student@cloudveil.demo"),
    ("Ravi Kumar", "ravi.student@cloudveil.demo"),
    ("Meera Nair", "meera.student@cloudveil.demo"),
]
_DEMO_OFFICERS = [
    ("Admissions Officer", "officer.admissions@cloudveil.demo"),
    ("Records Officer", "officer.records@cloudveil.demo"),
]
_DEMO_ADMIN = ("Demo Admin", "demo.admin@cloudveil.demo")
_DEMO_PASSWORD = "Demo@12345"

_DEMO_DOCS = [
    ("marks_card.pdf", "marks_card", _DEMO_PDF),
    (
        "transfer_certificate.txt",
        "transfer_certificate",
        b"FAKE Transfer Certificate for demo purposes only.\n",
    ),
    (
        "application_form.txt",
        "application_form",
        b"FAKE Application Form (demo). Not a real document.\n",
    ),
]


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


def _ensure_user(name, email, role):
    existing = User.query.filter_by(email=email).first()
    if existing:
        return existing
    return create_user(name, email, _DEMO_PASSWORD, role=role)


@click.command("seed-demo")
@with_appcontext
def seed_demo():
    """Seed fake demo users and documents (admissions use case). Idempotent.

    Uses only fabricated data — never real personal information.
    """
    from .files.service import create_file

    students = [_ensure_user(n, e, "student") for n, e in _DEMO_STUDENTS]
    for n, e in _DEMO_OFFICERS:
        _ensure_user(n, e, "officer")
    _ensure_user(*_DEMO_ADMIN, "admin")
    db.session.commit()

    from .models import File

    created = 0
    for student in students:
        if File.query.filter_by(owner_id=student.id, is_deleted=False).count():
            continue  # already has docs; don't duplicate on re-run
        for filename, category, data in _DEMO_DOCS:
            create_file(student, filename, data, category)
            created += 1
    click.echo(
        f"Demo ready: {len(_DEMO_STUDENTS)} students, {len(_DEMO_OFFICERS)} officers, "
        f"1 admin; {created} demo document(s) uploaded."
    )


def register_cli(app) -> None:
    app.cli.add_command(create_admin)
    app.cli.add_command(rewrap_keys)
    app.cli.add_command(seed_demo)
