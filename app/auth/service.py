"""Authentication service: password hashing, JWT issue/verify, lockout.

Separated from the HTTP layer so it can be unit-tested without a request
context. Passwords are hashed with bcrypt (cost 12). JWTs are HS256 with a
30-minute expiry and a unique ``jti``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from flask import current_app

from ..extensions import db
from ..models import User

BCRYPT_ROUNDS = 12
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


class AuthError(Exception):
    """Raised for authentication failures with a stable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_user(
    full_name: str, email: str, password: str, role: str = "student"
) -> User:
    """Create and persist a new user. Raises AuthError on duplicate email."""
    email = email.strip().lower()
    if User.query.filter_by(email=email).first():
        raise AuthError("email_taken", "An account with this email already exists.")
    user = User(
        full_name=full_name.strip(),
        email=email,
        password_hash=hash_password(password),
        role=role,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _is_locked(user: User, now: datetime) -> bool:
    return user.locked_until is not None and user.locked_until > now


def authenticate(email: str, password: str) -> User:
    """Return the user on success; raise AuthError otherwise.

    Tracks consecutive failures and locks the account for LOCKOUT_MINUTES after
    MAX_FAILED_LOGINS failures.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()

    if user is None:
        raise AuthError("invalid_credentials", "Invalid email or password.")
    if not user.is_active:
        raise AuthError("account_disabled", "This account is disabled.")
    if _is_locked(user, now):
        raise AuthError("account_locked", "Account locked. Try again later.")

    if not verify_password(password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        db.session.commit()
        raise AuthError("invalid_credentials", "Invalid email or password.")

    # Success: reset counters.
    user.failed_logins = 0
    user.locked_until = None
    db.session.commit()
    return user


def issue_jwt(user: User) -> str:
    now = datetime.now(UTC).replace(tzinfo=None)
    minutes = current_app.config.get("JWT_EXPIRY_MINUTES", 30)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    secret = current_app.config["JWT_SECRET"]
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str) -> dict:
    """Decode and validate a JWT. Raises AuthError if invalid/expired."""
    secret = current_app.config["JWT_SECRET"]
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token_expired", "Session expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("token_invalid", "Invalid session token.") from exc
