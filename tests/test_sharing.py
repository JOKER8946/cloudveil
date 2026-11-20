"""Sharing, revoke, metadata and error-path tests."""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from app.models import _utcnow
from tests.conftest import login


def _register(client, email):
    return client.post(
        "/api/auth/register",
        json={"full_name": "U", "email": email, "password": "password123"},
    )


def _upload(client, csrf, content=b"data here"):
    return client.post(
        "/api/files",
        data={"category": "marks_card", "file": (BytesIO(content), "n.txt")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    ).get_json()["file"]["id"]


def test_metadata_owner_and_intruder(client, app, make_user):
    make_user("intruder@example.com", role="officer")
    _register(client, "owner@example.com")
    csrf = login(client, "owner@example.com")
    file_id = _upload(client, csrf)

    meta = client.get(f"/api/files/{file_id}")
    assert meta.status_code == 200
    assert meta.get_json()["file"]["category"] == "marks_card"

    intruder = app.test_client()
    login(intruder, "intruder@example.com")
    assert intruder.get(f"/api/files/{file_id}").status_code == 403


def test_share_errors(client, app, make_user):
    make_user("stud2@example.com", role="student")
    _register(client, "owner@example.com")
    csrf = login(client, "owner@example.com")
    file_id = _upload(client, csrf)

    # Unknown user.
    r = client.post(
        f"/api/files/{file_id}/share",
        json={"grantee_email": "ghost@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404

    # Grantee is a student, not an officer.
    r = client.post(
        f"/api/files/{file_id}/share",
        json={"grantee_email": "stud2@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "invalid_grantee"


def test_share_with_expiry_then_revoke(client, app, make_user):
    officer = make_user("off@example.com", role="officer")
    _register(client, "owner@example.com")
    csrf = login(client, "owner@example.com")
    file_id = _upload(client, csrf, content=b"confidential")

    future = (_utcnow() + timedelta(hours=1)).isoformat()
    r = client.post(
        f"/api/files/{file_id}/share",
        json={"grantee_email": "off@example.com", "expires_at": future},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200

    off_client = app.test_client()
    login(off_client, "off@example.com")
    assert off_client.get(f"/api/files/{file_id}/download").status_code == 200

    # Owner revokes.
    rev = client.delete(
        f"/api/files/{file_id}/share/{officer['id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert rev.status_code == 200
    # Officer can no longer download.
    assert off_client.get(f"/api/files/{file_id}/download").status_code == 403
    # Revoking again -> 404 (no such share).
    assert (
        client.delete(
            f"/api/files/{file_id}/share/{officer['id']}",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )


def test_revoke_requires_owner_or_admin(client, app, make_user):
    officer = make_user("off@example.com", role="officer")
    _register(client, "owner@example.com")
    csrf = login(client, "owner@example.com")
    file_id = _upload(client, csrf)
    client.post(
        f"/api/files/{file_id}/share",
        json={"grantee_email": "off@example.com"},
        headers={"X-CSRF-Token": csrf},
    )

    # The officer (not owner/admin) cannot revoke.
    off_client = app.test_client()
    ocsrf = login(off_client, "off@example.com")
    resp = off_client.delete(
        f"/api/files/{file_id}/share/{officer['id']}",
        headers={"X-CSRF-Token": ocsrf},
    )
    assert resp.status_code == 403


def test_unwrap_failure_returns_502(client, app):
    """A broken key provider surfaces as KEY_UNWRAP_FAIL / 502."""
    _register(client, "s@example.com")
    csrf = login(client, "s@example.com")
    file_id = _upload(client, csrf, content=b"payload")

    class BrokenKP:
        def wrap(self, dek):  # pragma: no cover - not used here
            raise AssertionError

        def unwrap(self, wrapped_key, kek_key_id):
            raise RuntimeError("key vault unreachable")

    app.config["KEY_PROVIDER"] = BrokenKP()
    dl = client.get(f"/api/files/{file_id}/download")
    assert dl.status_code == 502
    assert dl.get_json()["error"]["code"] == "unwrap_failed"
