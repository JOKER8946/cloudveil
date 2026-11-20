"""Admin user-management API.

Admin-only. Role changes and activation toggles are audited as ADMIN_ACTION.
Audit-log viewing, stats and the benchmark endpoint are added in later phases.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..audit import logger
from ..auth.decorators import csrf_protect, get_current_user, require_role
from ..extensions import db
from ..models import AUDIT_ACTIONS, ROLES, AuditLog, File, User

bp = Blueprint("admin", __name__, url_prefix="/api/admin")
AUDIT_PAGE_SIZE = 25


@bp.get("/users")
@require_role("admin")
def list_users():
    role = request.args.get("role")
    query = User.query
    if role in ROLES:
        query = query.filter_by(role=role)
    users = query.order_by(User.created_at.desc()).all()
    return jsonify({"users": [u.to_dict() for u in users]})


@bp.get("/users/<int:user_id>")
@require_role("admin")
def get_user(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        return (
            jsonify({"error": {"code": "not_found", "message": "No such user."}}),
            404,
        )
    return jsonify({"user": user.to_dict()})


@bp.patch("/users/<int:user_id>")
@require_role("admin")
@csrf_protect
def update_user(user_id: int):
    actor = get_current_user()
    user = db.session.get(User, user_id)
    if user is None:
        return (
            jsonify({"error": {"code": "not_found", "message": "No such user."}}),
            404,
        )

    data = request.get_json(silent=True) or {}
    changes = {}

    if "role" in data:
        new_role = data["role"]
        if new_role not in ROLES:
            return (
                jsonify(
                    {"error": {"code": "invalid_input", "message": "Invalid role."}}
                ),
                400,
            )
        changes["role"] = new_role
        user.role = new_role

    if "is_active" in data:
        user.is_active = bool(data["is_active"])
        changes["is_active"] = user.is_active

    if changes:
        db.session.commit()
        logger.record(
            "ADMIN_ACTION",
            "success",
            user_id=actor.id,
            details={"target_user_id": user_id, "changes": changes},
        )
    return jsonify({"user": user.to_dict()})


@bp.get("/audit")
@require_role("admin")
def audit_log():
    """Paginated, filterable audit log."""
    query = AuditLog.query
    action = request.args.get("action")
    if action in AUDIT_ACTIONS:
        query = query.filter(AuditLog.action == action)
    user_id = request.args.get("user")
    if user_id and user_id.isdigit():
        query = query.filter(AuditLog.user_id == int(user_id))
    date_from = request.args.get("from")
    if date_from:
        query = query.filter(func.date(AuditLog.created_at) >= date_from)
    date_to = request.args.get("to")
    if date_to:
        query = query.filter(func.date(AuditLog.created_at) <= date_to)

    page = max(1, int(request.args.get("page", 1) or 1))
    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(AUDIT_PAGE_SIZE)
        .offset((page - 1) * AUDIT_PAGE_SIZE)
        .all()
    )
    return jsonify(
        {
            "items": [r.to_dict() for r in rows],
            "page": page,
            "page_size": AUDIT_PAGE_SIZE,
            "total": total,
            "pages": (total + AUDIT_PAGE_SIZE - 1) // AUDIT_PAGE_SIZE,
        }
    )


@bp.get("/stats")
@require_role("admin")
def stats():
    """Aggregate data for the admin dashboard charts (no secrets)."""
    uploads_by_day = (
        db.session.query(
            func.date(AuditLog.created_at).label("day"), func.count().label("n")
        )
        .filter(AuditLog.action == "UPLOAD")
        .group_by("day")
        .order_by("day")
        .all()
    )
    actions_by_type = (
        db.session.query(AuditLog.action, func.count()).group_by(AuditLog.action).all()
    )
    storage_by_category = (
        db.session.query(File.category, func.coalesce(func.sum(File.size_bytes), 0))
        .filter(File.is_deleted.is_(False))
        .group_by(File.category)
        .all()
    )
    downloads = AuditLog.query.filter(AuditLog.action == "DOWNLOAD").count()
    denials = AuditLog.query.filter(AuditLog.action == "DOWNLOAD_DENIED").count()

    return jsonify(
        {
            "uploads_by_day": [{"day": str(d), "count": n} for d, n in uploads_by_day],
            "actions_by_type": {a: n for a, n in actions_by_type},
            "storage_by_category": {c: int(s) for c, s in storage_by_category},
            "downloads_vs_denials": {"downloads": downloads, "denials": denials},
            "totals": {
                "users": User.query.count(),
                "files": File.query.filter(File.is_deleted.is_(False)).count(),
            },
        }
    )


@bp.post("/benchmark")
@require_role("admin")
@csrf_protect
def benchmark():
    """Server-side timings for AES-GCM, key wrap/unwrap and blob I/O.

    Uses synthetic random data written to temporary blobs that are deleted
    immediately — never stored as user files.
    """
    import os
    import time
    import uuid

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from ..providers import get_key_provider, get_storage

    data = request.get_json(silent=True) or {}
    default_sizes = [100 * 1024, 1024 * 1024, 10 * 1024 * 1024]
    sizes = data.get("sizes") or default_sizes
    sizes = [int(s) for s in sizes if 0 < int(s) <= 50 * 1024 * 1024][:6]

    kp = get_key_provider()
    storage = get_storage()

    dek = AESGCM.generate_key(bit_length=256)
    t = time.perf_counter()
    wrapped, kid = kp.wrap(dek)
    wrap_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    kp.unwrap(wrapped, kid)
    unwrap_ms = (time.perf_counter() - t) * 1000

    results = []
    for size in sizes:
        plaintext = os.urandom(size)
        nonce = os.urandom(12)
        aes = AESGCM(dek)
        t = time.perf_counter()
        ciphertext = aes.encrypt(nonce, plaintext, None)
        enc_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        aes.decrypt(nonce, ciphertext, None)
        dec_ms = (time.perf_counter() - t) * 1000

        blob_name = f"benchmark-{uuid.uuid4()}"
        t = time.perf_counter()
        storage.put(blob_name, ciphertext, file_id="benchmark")
        put_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        storage.get(blob_name)
        get_ms = (time.perf_counter() - t) * 1000
        storage.delete(blob_name)

        results.append(
            {
                "size_bytes": size,
                "aes_encrypt_ms": round(enc_ms, 3),
                "aes_decrypt_ms": round(dec_ms, 3),
                "blob_put_ms": round(put_ms, 2),
                "blob_get_ms": round(get_ms, 2),
            }
        )
    del dek

    logger.record(
        "ADMIN_ACTION",
        "success",
        user_id=get_current_user().id,
        details={"benchmark_sizes": sizes},
    )
    return jsonify(
        {
            "key_wrap_ms": round(wrap_ms, 3),
            "key_unwrap_ms": round(unwrap_ms, 3),
            "results": results,
        }
    )
