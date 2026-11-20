"""Shared pytest fixtures.

Tests run entirely in-process against SQLite in-memory and in-memory fakes;
no Azure services or MySQL are contacted.
"""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture
def app():
    """Create a Flask app configured for testing with a fresh schema."""
    app = create_app("test")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """A Flask test client."""
    return app.test_client()
