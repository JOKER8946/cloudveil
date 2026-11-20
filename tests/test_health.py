"""Health endpoint tests.

In the test configuration Key Vault and Blob Storage are not configured, so
those checks report 'disabled' (never 'error') and the overall status is 'ok'.
"""

from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "cloudveil"


def test_health_reports_checks(client):
    body = client.get("/api/health").get_json()
    checks = body["checks"]
    # SQLite in-memory is reachable in tests.
    assert checks["database"] == "ok"
    # Azure endpoints are not configured under TestConfig.
    assert checks["keyvault"] == "disabled"
    assert checks["blob"] == "disabled"
