"""Auth tests: registration, login success/failure, lockout, role guard, CSRF."""

from __future__ import annotations

from app.auth.decorators import require_role


def _register(
    client, email="student@example.com", password="password123", name="Stu Dent"
):
    return client.post(
        "/api/auth/register",
        json={"full_name": name, "email": email, "password": password},
    )


def _login(client, email="student@example.com", password="password123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _csrf_from(resp):
    for header in resp.headers.getlist("Set-Cookie"):
        if header.startswith("cv_csrf="):
            return header.split(";")[0].split("=", 1)[1]
    return None


def test_register_creates_student(client):
    resp = _register(client)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["user"]["role"] == "student"
    assert body["user"]["email"] == "student@example.com"


def test_register_rejects_short_password(client):
    resp = _register(client, password="short")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_input"


def test_register_duplicate_email(client):
    _register(client)
    resp = _register(client)
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "email_taken"


def test_login_success_sets_cookies_and_me(client):
    _register(client)
    resp = _login(client)
    assert resp.status_code == 200
    cookies = " ".join(resp.headers.getlist("Set-Cookie"))
    assert "cv_access=" in cookies
    assert "HttpOnly" in cookies  # access cookie is HttpOnly
    assert "cv_csrf=" in cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["user"]["email"] == "student@example.com"


def test_login_wrong_password(client):
    _register(client)
    resp = _login(client, password="wrongpassword")
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "invalid_credentials"


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_lockout_after_five_failures(client):
    _register(client)
    for _ in range(5):
        client.post(
            "/api/auth/login",
            json={"email": "student@example.com", "password": "bad"},
        )
    # Even the correct password is now refused: the account is locked.
    resp = _login(client)
    assert resp.status_code == 423
    assert resp.get_json()["error"]["code"] == "account_locked"


def test_role_guard_blocks_wrong_role(app, client):
    @require_role("admin")
    def admin_only():
        return {"ok": True}

    app.add_url_rule("/_test/admin-only", "admin_only", admin_only)

    # Unauthenticated -> 401
    assert client.get("/_test/admin-only").status_code == 401

    # Authenticated as student -> 403
    _register(client)
    _login(client)
    assert client.get("/_test/admin-only").status_code == 403


def test_logout_requires_csrf(client):
    _register(client)
    login = _login(client)
    csrf = _csrf_from(login)
    assert csrf

    # Missing CSRF header -> rejected.
    assert client.post("/api/auth/logout").status_code == 403

    # Correct CSRF header -> ok, and session ends.
    resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
