"""SQLAlchemy models for CloudVeil (MySQL utf8mb4 in production).

Types are declared portably so the same models work on SQLite (CI tests) and
MySQL (production). Where the spec calls for a MySQL-specific type (e.g.
``VARBINARY``), ``with_variant`` renders it on MySQL while falling back to a
portable type on SQLite.

No column ever stores a plaintext data key — only the *wrapped* key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects import mysql

from .extensions import db


def _utcnow() -> datetime:
    # Naive UTC: the DateTime columns are timezone-naive, so every datetime we
    # store or compare must be naive UTC to avoid aware/naive mismatches.
    return datetime.now(UTC).replace(tzinfo=None)


def _uuid() -> str:
    return str(uuid.uuid4())


# VARBINARY on MySQL, BLOB on SQLite — used for nonce and wrapped key bytes.
def _varbinary(length: int):
    return db.LargeBinary(length).with_variant(mysql.VARBINARY(length), "mysql")


ROLES = ("student", "officer", "admin")
CATEGORIES = (
    "marks_card",
    "id_document",
    "transfer_certificate",
    "application_form",
    "other",
)
AUDIT_ACTIONS = (
    "LOGIN",
    "LOGIN_FAILED",
    "LOGOUT",
    "UPLOAD",
    "DOWNLOAD",
    "DOWNLOAD_DENIED",
    "SHARE",
    "REVOKE",
    "DELETE",
    "INTEGRITY_FAIL",
    "KEY_UNWRAP_FAIL",
    "ADMIN_ACTION",
)
AUDIT_STATUSES = ("success", "denied", "error")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum(*ROLES, name="user_role"), nullable=False, default="student"
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    files = db.relationship(
        "File", back_populates="owner", foreign_keys="File.owner_id"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class File(db.Model):
    __tablename__ = "files"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    original_name = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(128), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    blob_name = db.Column(db.String(64), nullable=False, unique=True)
    nonce = db.Column(_varbinary(12), nullable=False)
    wrapped_key = db.Column(_varbinary(512), nullable=False)
    kek_key_id = db.Column(db.String(512), nullable=False)
    wrap_alg = db.Column(db.String(32), nullable=False, default="RSA-OAEP-256")
    sha256 = db.Column(db.String(64), nullable=False)
    primary_region = db.Column(db.String(64), nullable=True)
    category = db.Column(
        db.Enum(*CATEGORIES, name="file_category"), nullable=False, default="other"
    )
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    owner = db.relationship("User", back_populates="files", foreign_keys=[owner_id])
    permissions = db.relationship(
        "FilePermission", back_populates="file", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "original_name": self.original_name,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "sha256_short": self.sha256[:12] if self.sha256 else None,
            "category": self.category,
            "primary_region": self.primary_region,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FilePermission(db.Model):
    __tablename__ = "file_permissions"
    __table_args__ = (
        db.UniqueConstraint("file_id", "grantee_id", name="uq_file_grantee"),
    )

    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(
        db.String(36), db.ForeignKey("files.id"), nullable=False, index=True
    )
    grantee_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    can_download = db.Column(db.Boolean, nullable=False, default=True)
    granted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    file = db.relationship("File", back_populates="permissions")
    grantee = db.relationship("User", foreign_keys=[grantee_id])


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    # BIGINT on MySQL; INTEGER on SQLite so its rowid autoincrement works.
    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    action = db.Column(
        db.Enum(*AUDIT_ACTIONS, name="audit_action"), nullable=False, index=True
    )
    file_id = db.Column(db.String(36), nullable=True)
    status = db.Column(db.Enum(*AUDIT_STATUSES, name="audit_status"), nullable=False)
    ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "file_id": self.file_id,
            "status": self.status,
            "ip": self.ip,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
