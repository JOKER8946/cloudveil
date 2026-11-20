"""File service: encrypt-on-upload, authorize-and-decrypt-on-download, sharing.

All authorization flows through :func:`can_download`, which is unit-tested for
every role x ownership x permission x expiry combination. Admins get **no**
automatic decrypt access — they must hold an explicit (self-granted, audited)
permission just like anyone else.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from cryptography.exceptions import InvalidTag

from ..audit import logger
from ..crypto.envelope import decrypt_file, encrypt_file
from ..crypto.integrity import verify_sha256
from ..extensions import db
from ..models import CATEGORIES, File, FilePermission, User, _utcnow
from ..providers import get_key_provider, get_storage

ALLOWED_EXT = {"pdf", "png", "jpg", "jpeg", "docx", "txt"}
MAGIC = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "docx": [b"PK\x03\x04"],
    "txt": [],  # no reliable magic; accepted by extension
}
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


class FileError(Exception):
    """Service error carrying an HTTP status + stable code."""

    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def validate_upload(filename: str, data: bytes) -> str:
    """Validate extension AND magic bytes; return the normalized extension."""
    ext = _ext_of(filename)
    if ext not in ALLOWED_EXT:
        raise FileError("unsupported_type", f"File type .{ext} is not allowed.", 400)
    magics = MAGIC[ext]
    if magics and not any(data.startswith(m) for m in magics):
        raise FileError(
            "content_mismatch", "File content does not match its extension.", 400
        )
    return ext


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #
def active_permission(file_id: str, user_id: int) -> FilePermission | None:
    perm = FilePermission.query.filter_by(
        file_id=file_id, grantee_id=user_id, can_download=True
    ).first()
    if perm is None:
        return None
    if perm.expires_at is not None and perm.expires_at <= _utcnow():
        return None
    return perm


def can_download(user: User, file: File) -> bool:
    """The single source of truth for download authorization."""
    if user is None or file is None or file.is_deleted:
        return False
    if file.owner_id == user.id:
        return True
    return active_permission(file.id, user.id) is not None


# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #
def create_file(owner: User, filename: str, data: bytes, category: str) -> File:
    if not data:
        raise FileError("empty_file", "The uploaded file is empty.", 400)
    ext = validate_upload(filename, data)
    if category not in CATEGORIES:
        category = "other"

    from flask import current_app

    file_id = str(uuid.uuid4())
    enc = encrypt_file(
        data, file_id=file_id, owner_id=owner.id, key_provider=get_key_provider()
    )
    blob_name = str(uuid.uuid4())
    get_storage().put(blob_name, enc.ciphertext, file_id=file_id)

    record = File(
        id=file_id,
        owner_id=owner.id,
        original_name=(filename or "upload")[:255],
        content_type=CONTENT_TYPES.get(ext, "application/octet-stream"),
        size_bytes=len(data),
        blob_name=blob_name,
        nonce=enc.nonce,
        wrapped_key=enc.wrapped_key,
        kek_key_id=enc.kek_key_id,
        wrap_alg=enc.wrap_alg,
        sha256=enc.sha256,
        primary_region=current_app.config.get("PRIMARY_REGION", ""),
        category=category,
    )
    db.session.add(record)
    db.session.commit()
    logger.record(
        "UPLOAD",
        "success",
        user_id=owner.id,
        file_id=file_id,
        details={"size": len(data), "category": category},
    )
    return record


def list_own(user: User) -> list[File]:
    return (
        File.query.filter_by(owner_id=user.id, is_deleted=False)
        .order_by(File.created_at.desc())
        .all()
    )


def list_shared_with(user: User) -> list[File]:
    now = _utcnow()
    rows = (
        db.session.query(File)
        .join(FilePermission, FilePermission.file_id == File.id)
        .filter(
            FilePermission.grantee_id == user.id,
            FilePermission.can_download.is_(True),
            File.is_deleted.is_(False),
        )
        .filter(
            (FilePermission.expires_at.is_(None)) | (FilePermission.expires_at > now)
        )
        .order_by(File.created_at.desc())
        .all()
    )
    return rows


def get_file_or_404(file_id: str) -> File:
    record = db.session.get(File, file_id)
    if record is None or record.is_deleted:
        raise FileError("not_found", "File not found.", 404)
    return record


def download(user: User, file: File) -> tuple[bytes, File]:
    if not can_download(user, file):
        logger.record("DOWNLOAD_DENIED", "denied", user_id=user.id, file_id=file.id)
        raise FileError("forbidden", "You cannot download this file.", 403)

    try:
        ciphertext = get_storage().get(file.blob_name)
    except Exception as exc:  # blob missing / storage error
        logger.record("DOWNLOAD", "error", user_id=user.id, file_id=file.id)
        raise FileError("storage_error", "Stored file unavailable.", 502) from exc

    try:
        plaintext = decrypt_file(
            ciphertext,
            nonce=file.nonce,
            wrapped_key=file.wrapped_key,
            kek_key_id=file.kek_key_id,
            file_id=file.id,
            owner_id=file.owner_id,
            key_provider=get_key_provider(),
        )
    except InvalidTag as exc:
        logger.record("INTEGRITY_FAIL", "error", user_id=user.id, file_id=file.id)
        raise FileError(
            "integrity_failed", "File integrity check failed.", 409
        ) from exc
    except Exception as exc:
        logger.record("KEY_UNWRAP_FAIL", "error", user_id=user.id, file_id=file.id)
        raise FileError("unwrap_failed", "Could not unwrap file key.", 502) from exc

    if not verify_sha256(plaintext, file.sha256):
        logger.record("INTEGRITY_FAIL", "error", user_id=user.id, file_id=file.id)
        raise FileError("integrity_failed", "File integrity check failed.", 409)

    logger.record("DOWNLOAD", "success", user_id=user.id, file_id=file.id)
    return plaintext, file


def share(owner: User, file: File, grantee_email: str, expires_at: str | None):
    if file.owner_id != owner.id:
        raise FileError("forbidden", "Only the owner can share this file.", 403)
    grantee = User.query.filter_by(email=(grantee_email or "").strip().lower()).first()
    if grantee is None:
        raise FileError("no_such_user", "No user with that email.", 404)
    if grantee.id == owner.id:
        raise FileError("invalid_grantee", "You already own this file.", 400)
    if grantee.role != "officer":
        raise FileError(
            "invalid_grantee", "Files can only be shared with officers.", 400
        )

    expiry = _parse_expiry(expires_at)
    perm = FilePermission.query.filter_by(
        file_id=file.id, grantee_id=grantee.id
    ).first()
    if perm is None:
        perm = FilePermission(
            file_id=file.id, grantee_id=grantee.id, granted_by=owner.id
        )
        db.session.add(perm)
    perm.can_download = True
    perm.granted_by = owner.id
    perm.expires_at = expiry
    db.session.commit()
    logger.record(
        "SHARE",
        "success",
        user_id=owner.id,
        file_id=file.id,
        details={"grantee_id": grantee.id, "expires_at": expires_at},
    )
    return perm


def revoke(actor: User, file: File, grantee_id: int):
    is_owner = file.owner_id == actor.id
    is_admin = actor.role == "admin"
    if not (is_owner or is_admin):
        raise FileError("forbidden", "Not allowed to revoke on this file.", 403)
    perm = FilePermission.query.filter_by(
        file_id=file.id, grantee_id=grantee_id
    ).first()
    if perm is None:
        raise FileError("not_found", "No such share.", 404)
    db.session.delete(perm)
    db.session.commit()
    action = "ADMIN_ACTION" if (is_admin and not is_owner) else "REVOKE"
    logger.record(
        action,
        "success",
        user_id=actor.id,
        file_id=file.id,
        details={"revoked_grantee_id": grantee_id},
    )


def delete_file(owner: User, file: File):
    if file.owner_id != owner.id:
        raise FileError("forbidden", "Only the owner can delete this file.", 403)
    file.is_deleted = True
    db.session.commit()
    try:
        get_storage().delete(file.blob_name)
    except Exception:
        pass  # metadata soft-deleted regardless; blob cleanup is best-effort
    logger.record("DELETE", "success", user_id=owner.id, file_id=file.id)


def _parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FileError("invalid_input", "Invalid expires_at.", 400) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed
