"""Request-level auth helpers: current user, role guard, CSRF.

The JWT lives in an HttpOnly cookie. CSRF uses the double-submit pattern: a
non-HttpOnly cookie whose value the browser JS echoes back in the
``X-CSRF-Token`` header on every state-changing request.
"""

from __future__ import annotations

import hmac
from functools import wraps

from flask import g, jsonify, request

from ..extensions import db
from ..models import User
from .service import AuthError, decode_jwt

ACCESS_COOKIE = "cv_access"
CSRF_COOKIE = "cv_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def get_current_user() -> User | None:
    """Resolve the authenticated user from the JWT cookie (cached on g)."""
    if "current_user" in g:
        return g.current_user
    user = None
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        try:
            claims = decode_jwt(token)
            user = db_get_active_user(int(claims["sub"]))
        except (AuthError, KeyError, ValueError, TypeError):
            user = None
    g.current_user = user
    return user


def db_get_active_user(user_id: int) -> User | None:
    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if get_current_user() is None:
            return _error("unauthenticated", "Authentication required.", 401)
        return func(*args, **kwargs)

    return wrapper


def require_role(*roles: str):
    """Allow only users whose role is in ``roles``."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return _error("unauthenticated", "Authentication required.", 401)
            if user.role not in roles:
                return _error("forbidden", "You do not have permission.", 403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def csrf_protect(func):
    """Reject state-changing requests without a matching CSRF token."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            cookie = request.cookies.get(CSRF_COOKIE)
            header = request.headers.get(CSRF_HEADER)
            if not cookie or not header or not hmac.compare_digest(cookie, header):
                return _error("csrf_failed", "CSRF token missing or invalid.", 403)
        return func(*args, **kwargs)

    return wrapper
