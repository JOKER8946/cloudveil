"""Liveness / readiness endpoint.

Probes the three external dependencies — MySQL, Key Vault and Blob Storage —
and reports each one's reachability. No secrets, connection strings or key
material ever appear in the output.

Azure SDK clients are imported and constructed lazily inside each check so that:
  * unit tests (where the Azure endpoints are not configured) never touch the
    network or require managed-identity credentials, and
  * application cold-start stays fast and cannot fail on an SDK import.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from ..extensions import db

bp = Blueprint("health", __name__)


def _check_database() -> str:
    """Return 'ok' if a trivial query succeeds, else 'error'."""
    try:
        db.session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        db.session.rollback()
        return "error"


def _check_keyvault() -> str:
    """Return 'ok' if the KEK is readable, 'disabled' if not configured."""
    url = current_app.config.get("KEYVAULT_URL")
    if not url:
        return "disabled"
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.keys import KeyClient

        client = KeyClient(vault_url=url, credential=DefaultAzureCredential())
        client.get_key(current_app.config.get("KEK_NAME", "cloudveil-kek"))
        return "ok"
    except Exception:
        return "error"


def _check_blob() -> str:
    """Return 'ok' if the container is reachable, 'disabled' if not configured."""
    account_url = current_app.config.get("STORAGE_ACCOUNT_URL")
    if not account_url:
        return "disabled"
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        svc = BlobServiceClient(
            account_url=account_url, credential=DefaultAzureCredential()
        )
        container = svc.get_container_client(
            current_app.config.get("STORAGE_CONTAINER", "encrypted-files")
        )
        container.get_container_properties()
        return "ok"
    except Exception:
        return "error"


@bp.get("/api/health")
def health():
    """Report liveness of the app and its dependencies."""
    checks = {
        "database": _check_database(),
        "keyvault": _check_keyvault(),
        "blob": _check_blob(),
    }
    healthy = all(status != "error" for status in checks.values())
    body = {
        "status": "ok" if healthy else "degraded",
        "service": "cloudveil",
        "checks": checks,
    }
    return jsonify(body), (200 if healthy else 503)
