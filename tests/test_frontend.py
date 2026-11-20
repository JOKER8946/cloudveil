"""Frontend pages render."""

from __future__ import annotations


def test_pages_render(client):
    for path in ("/", "/how-it-works", "/app"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert b"CloudVeil" in resp.data


def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in resp.headers
