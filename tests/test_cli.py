"""CLI command tests (create-admin, rewrap-keys)."""

from __future__ import annotations

from io import BytesIO

from tests.conftest import login


def test_rewrap_keys_rotates_and_keeps_file_readable(client, app):
    client.post(
        "/api/auth/register",
        json={"full_name": "S", "email": "s@example.com", "password": "password123"},
    )
    csrf = login(client, "s@example.com")
    up = client.post(
        "/api/files",
        data={"category": "other", "file": (BytesIO(b"rotate me"), "n.txt")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    file_id = up.get_json()["file"]["id"]

    result = app.test_cli_runner().invoke(args=["rewrap-keys"])
    assert result.exit_code == 0
    assert "Re-wrapped 1" in result.output

    # File is still decryptable after re-wrapping.
    dl = client.get(f"/api/files/{file_id}/download")
    assert dl.status_code == 200
    assert dl.data == b"rotate me"


def test_seed_demo_creates_users_and_docs(app):
    from app.models import File, User

    result = app.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code == 0
    with app.app_context():
        assert User.query.filter_by(role="student").count() >= 3
        assert User.query.filter_by(role="officer").count() >= 2
        assert File.query.count() >= 3

    # Idempotent: running again does not duplicate documents.
    before = None
    with app.app_context():
        before = File.query.count()
    app.test_cli_runner().invoke(args=["seed-demo"])
    with app.app_context():
        assert File.query.count() == before
