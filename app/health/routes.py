"""Liveness endpoint.

Phase 1: a simple always-OK response so CI and the first deploy have a stable
target. Phase 3 extends this to probe the database, Key Vault and Blob Storage
(without ever leaking secrets in the output).
"""

from __future__ import annotations

from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.get("/api/health")
def health():
    """Return a minimal liveness payload."""
    return jsonify({"status": "ok", "service": "cloudveil"}), 200
