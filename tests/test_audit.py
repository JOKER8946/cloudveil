"""Audit logging tests: actions are recorded with the right status."""

from __future__ import annotations

from io import BytesIO

from app.models import AuditLog
from tests.conftest import login


def _actions(app, **filters):
    with app.app_context():
        q = AuditLog.query
        if filters:
            q = q.filter_by(**filters)
        return [row.action for row in q.all()]


def test_login_and_upload_audited(client, app):
    client.post(
        "/api/auth/register",
        json={"full_name": "S", "email": "s@example.com", "password": "password123"},
    )
    csrf = login(client, "s@example.com")
    client.post(
        "/api/files",
        data={"category": "other", "file": (BytesIO(b"hi there"), "n.txt")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    actions = _actions(app)
    assert "LOGIN" in actions
    assert "UPLOAD" in actions


def test_failed_login_audited(client, app):
    client.post(
        "/api/auth/register",
        json={"full_name": "S", "email": "s@example.com", "password": "password123"},
    )
    client.post("/api/auth/login", json={"email": "s@example.com", "password": "nope"})
    assert "LOGIN_FAILED" in _actions(app, action="LOGIN_FAILED")


def test_denied_download_audited(client, app, make_user):
    make_user("intruder@example.com", role="officer")
    client.post(
        "/api/auth/register",
        json={
            "full_name": "O",
            "email": "owner@example.com",
            "password": "password123",
        },
    )
    csrf = login(client, "owner@example.com")
    file_id = client.post(
        "/api/files",
        data={"category": "other", "file": (BytesIO(b"x"), "n.txt")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    ).get_json()["file"]["id"]

    intruder = app.test_client()
    login(intruder, "intruder@example.com")
    intruder.get(f"/api/files/{file_id}/download")
    assert "DOWNLOAD_DENIED" in _actions(app, action="DOWNLOAD_DENIED")
