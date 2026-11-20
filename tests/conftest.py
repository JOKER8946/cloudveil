"""Shared pytest fixtures.

Tests run entirely in-process against SQLite in-memory (shared via StaticPool)
and in-memory fakes (FakeKeyProvider / FakeStorage); no Azure services or MySQL
are contacted.

The app context is held only while creating/dropping the schema — NOT while the
test client makes requests — so each request gets its own request/app context
(and a fresh ``flask.g``), exactly like production.
"""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db as _db
from tests.fakes import FakeKeyProvider, FakeStorage


@pytest.fixture
def app():
    """Flask app configured for testing with fresh schema + injected fakes."""
    app = create_app("test")
    app.config["KEY_PROVIDER"] = FakeKeyProvider()
    app.config["STORAGE_BACKEND"] = FakeStorage()
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def storage(app):
    """The injected in-memory FakeStorage (for tamper tests)."""
    return app.config["STORAGE_BACKEND"]


@pytest.fixture
def make_user(app):
    """Factory creating a user directly; returns a detached dict of its fields."""

    def _make(email, password="password123", role="student", name="Test User"):
        from app.auth.service import create_user

        with app.app_context():
            user = create_user(name, email, password, role=role)
            return {"id": user.id, "email": user.email, "role": user.role}

    return _make


def login(client, email, password="password123"):
    """Log the client in; return the CSRF token for state-changing requests."""
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    csrf = None
    for header in resp.headers.getlist("Set-Cookie"):
        if header.startswith("cv_csrf="):
            csrf = header.split(";")[0].split("=", 1)[1]
    return csrf
