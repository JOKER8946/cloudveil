"""Authentication HTTP routes: register, login, logout, me."""

from __future__ import annotations

import re
import secrets

from flask import Blueprint, current_app, jsonify, make_response, request

from ..audit import logger
from ..extensions import limiter
from .decorators import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    csrf_protect,
    get_current_user,
)
from .service import AuthError, authenticate, create_user, issue_jwt

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8


def _err(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def _set_session_cookies(resp, token: str):
    secure = current_app.config.get("SESSION_COOKIE_SECURE", True)
    max_age = current_app.config.get("JWT_EXPIRY_MINUTES", 30) * 60
    csrf = secrets.token_urlsafe(32)
    resp.set_cookie(
        ACCESS_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="Strict",
        path="/",
    )
    resp.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="Strict",
        path="/",
    )
    return resp


@bp.post("/register")
def register():
    """Public registration — always creates a 'student'."""
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not full_name:
        return _err("invalid_input", "Full name is required.", 400)
    if not EMAIL_RE.match(email):
        return _err("invalid_input", "A valid email is required.", 400)
    if len(password) < MIN_PASSWORD_LEN:
        return _err(
            "invalid_input",
            f"Password must be at least {MIN_PASSWORD_LEN} characters.",
            400,
        )

    try:
        user = create_user(full_name, email, password, role="student")
    except AuthError as exc:
        return _err(exc.code, exc.message, 409)
    return jsonify({"user": user.to_dict()}), 201


@bp.post("/login")
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    try:
        user = authenticate(email, password)
    except AuthError as exc:
        logger.record("LOGIN_FAILED", "denied", details={"email": email[:255]})
        status = 423 if exc.code == "account_locked" else 401
        return _err(exc.code, exc.message, status)

    token = issue_jwt(user)
    logger.record("LOGIN", "success", user_id=user.id)
    resp = make_response(jsonify({"user": user.to_dict()}))
    return _set_session_cookies(resp, token)


@bp.post("/logout")
@csrf_protect
def logout():
    user = get_current_user()
    resp = make_response(jsonify({"status": "ok"}))
    resp.delete_cookie(ACCESS_COOKIE, path="/")
    resp.delete_cookie(CSRF_COOKIE, path="/")
    if user is not None:
        logger.record("LOGOUT", "success", user_id=user.id)
    return resp


@bp.get("/me")
def me():
    user = get_current_user()
    if user is None:
        return _err("unauthenticated", "Authentication required.", 401)
    return jsonify({"user": user.to_dict()})
