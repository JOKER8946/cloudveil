"""Admin user-management tests."""

from __future__ import annotations

from tests.conftest import login


def test_admin_lists_and_promotes(client, app, make_user):
    make_user("admin@example.com", role="admin")
    target = make_user("user@example.com", role="student")
    csrf = login(client, "admin@example.com")

    listing = client.get("/api/admin/users")
    assert listing.status_code == 200
    assert len(listing.get_json()["users"]) == 2

    patch = client.patch(
        f"/api/admin/users/{target['id']}",
        json={"role": "officer"},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch.status_code == 200
    assert patch.get_json()["user"]["role"] == "officer"


def test_admin_rejects_invalid_role(client, app, make_user):
    make_user("admin@example.com", role="admin")
    target = make_user("user@example.com", role="student")
    csrf = login(client, "admin@example.com")
    resp = client.patch(
        f"/api/admin/users/{target['id']}",
        json={"role": "superuser"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 400


def test_non_admin_forbidden(client, app, make_user):
    make_user("student@example.com", role="student")
    login(client, "student@example.com")
    assert client.get("/api/admin/users").status_code == 403
