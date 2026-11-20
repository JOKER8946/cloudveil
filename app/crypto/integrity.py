"""Content integrity helpers (SHA-256)."""

from __future__ import annotations

import hashlib
import hmac


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_sha256(data: bytes, expected_hex: str) -> bool:
    """Constant-time comparison of SHA-256(data) against an expected digest."""
    actual = hashlib.sha256(data).hexdigest()
    return hmac.compare_digest(actual, expected_hex)
