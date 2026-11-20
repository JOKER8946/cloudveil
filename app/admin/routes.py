"""Admin user-management API.

Admin-only. Role changes and activation toggles are audited as ADMIN_ACTION.
Audit-log viewing, stats and the benchmark endpoint are added in later phases.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..audit import logger
from ..auth.decorators import csrf_protect, get_current_user, require_role
from ..extensions import db
from ..models import ROLES, User

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


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
