"""Files API integration tests (upload/list/share/download/revoke/delete/tamper)."""

from __future__ import annotations

from io import BytesIO

from app.extensions import db
from app.models import File
from tests.conftest import login


def _upload(
    client, csrf, content=b"hello cloudveil", name="note.txt", category="other"
):
    return client.post(
        "/api/files",
        data={"category": category, "file": (BytesIO(content), name)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


def _register(client, email, name="Stu"):
    return client.post(
        "/api/auth/register",
        json={"full_name": name, "email": email, "password": "password123"},
    )


def test_upload_list_download_roundtrip(client):
    _register(client, "s@example.com")
    csrf = login(client, "s@example.com")

    up = _upload(client, csrf, content=b"secret contents")
    assert up.status_code == 201
    file_id = up.get_json()["file"]["id"]

    listing = client.get("/api/files")
    assert listing.status_code == 200
    assert len(listing.get_json()["files"]) == 1

    dl = client.get(f"/api/files/{file_id}/download")
    assert dl.status_code == 200
    assert dl.data == b"secret contents"
    assert "attachment" in dl.headers["Content-Disposition"]


def test_upload_rejects_bad_magic(client):
    _register(client, "s@example.com")
    csrf = login(client, "s@example.com")
    # .png extension but not PNG bytes.
    resp = _upload(client, csrf, content=b"not a real png", name="fake.png")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "content_mismatch"


def test_share_and_officer_download(client, app, make_user):
    make_user("officer@example.com", role="officer")
    _register(client, "owner@example.com")
    csrf = login(client, "owner@example.com")
    file_id = _upload(client, csrf, content=b"share me").get_json()["file"]["id"]

    share = client.post(
        f"/api/files/{file_id}/share",
        json={"grantee_email": "officer@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert share.status_code == 200

    officer = app.test_client()
    ocsrf = login(officer, "officer@example.com")
    assert ocsrf
    shared = officer.get("/api/files/shared")
    assert shared.status_code == 200
    assert any(f["id"] == file_id for f in shared.get_json()["files"])

    dl = officer.get(f"/api/files/{file_id}/download")
    assert dl.status_code == 200
    assert dl.data == b"share me"


def test_unauthorized_download_forbidden(client, app, make_user):
    make_user("intruder@example.com", role="officer")
    _register(client, "owner@example.com")
    csrf = login(client, "owner@example.com")
    file_id = _upload(client, csrf, content=b"private").get_json()["file"]["id"]

    intruder = app.test_client()
    login(intruder, "intruder@example.com")
    dl = intruder.get(f"/api/files/{file_id}/download")
    assert dl.status_code == 403
    assert dl.get_json()["error"]["code"] == "forbidden"


def test_tampered_blob_returns_409(client, app, storage):
    _register(client, "s@example.com")
    csrf = login(client, "s@example.com")
    file_id = _upload(client, csrf, content=b"authentic").get_json()["file"]["id"]

    with app.app_context():
        blob_name = db.session.get(File, file_id).blob_name
    storage.overwrite_raw(blob_name, b"corrupted-ciphertext-bytes")

    dl = client.get(f"/api/files/{file_id}/download")
    assert dl.status_code == 409
    assert dl.get_json()["error"]["code"] == "integrity_failed"


def test_delete_soft_deletes_and_hides(client):
    _register(client, "s@example.com")
    csrf = login(client, "s@example.com")
    file_id = _upload(client, csrf).get_json()["file"]["id"]

    d = client.delete(f"/api/files/{file_id}", headers={"X-CSRF-Token": csrf})
    assert d.status_code == 200
    assert client.get("/api/files").get_json()["files"] == []
    assert client.get(f"/api/files/{file_id}/download").status_code == 404


def test_upload_requires_student_role(client, app, make_user):
    make_user("officer@example.com", role="officer")
    officer = app.test_client()
    csrf = login(officer, "officer@example.com")
    resp = _upload(officer, csrf)
    assert resp.status_code == 403
