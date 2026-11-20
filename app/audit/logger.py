"""Append-only audit logging.

Audit rows are only ever inserted — there are no update or delete routes. The
client IP comes from ``request.remote_addr`` after ProxyFix has applied
``X-Forwarded-For`` (App Service sits behind a reverse proxy).
"""

from __future__ import annotations

from typing import Any

from flask import has_request_context, request

from ..extensions import db
from ..models import AuditLog


def _client_ip() -> str | None:
    if not has_request_context():
        return None
    return request.remote_addr


def _user_agent() -> str | None:
    if not has_request_context():
        return None
    ua = request.headers.get("User-Agent", "")
    return ua[:512] if ua else None


def record(
    action: str,
    status: str,
    *,
    user_id: int | None = None,
    file_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Insert one audit row and commit it."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        status=status,
        file_id=file_id,
        ip=_client_ip(),
        user_agent=_user_agent(),
        details=details,
    )
    db.session.add(entry)
    db.session.commit()
