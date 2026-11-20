"""Authorization matrix for can_download: role x ownership x permission x expiry."""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.auth.service import create_user
from app.extensions import db
from app.files.service import can_download
from app.models import File, FilePermission, _utcnow


def _make_file(owner_id: int) -> File:
    record = File(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        original_name="doc.txt",
        content_type="text/plain",
        size_bytes=3,
        blob_name=str(uuid.uuid4()),
        nonce=b"0" * 12,
        wrapped_key=b"0" * 32,
        kek_key_id="kek",
        wrap_alg="RSA-OAEP-256",
        sha256="0" * 64,
        category="other",
    )
    db.session.add(record)
    db.session.commit()
    return record


def _grant(file, grantee_id, owner_id, *, can=True, expires_at=None):
    perm = FilePermission(
        file_id=file.id,
        grantee_id=grantee_id,
        granted_by=owner_id,
        can_download=can,
        expires_at=expires_at,
    )
    db.session.add(perm)
    db.session.commit()
    return perm


def test_can_download_matrix(app):
    with app.app_context():
        owner = create_user("Owner", "owner@example.com", "password123", role="student")
        officer = create_user("Off", "off@example.com", "password123", role="officer")
        officer2 = create_user(
            "Off2", "off2@example.com", "password123", role="officer"
        )
        admin = create_user("Adm", "adm@example.com", "password123", role="admin")

        f = _make_file(owner.id)

        # Owner always can.
        assert can_download(owner, f) is True

        # Officer without a permission cannot.
        assert can_download(officer, f) is False

        # Admin gets NO automatic access.
        assert can_download(admin, f) is False

        # Officer with an active permission can.
        _grant(f, officer.id, owner.id)
        assert can_download(officer, f) is True

        # Officer with an expired permission cannot.
        _grant(f, officer2.id, owner.id, expires_at=_utcnow() - timedelta(minutes=1))
        assert can_download(officer2, f) is False

        # A revoked (can_download=False) permission cannot.
        perm = FilePermission.query.filter_by(
            file_id=f.id, grantee_id=officer.id
        ).first()
        perm.can_download = False
        db.session.commit()
        assert can_download(officer, f) is False

        # Soft-deleted file: even the owner cannot.
        f.is_deleted = True
        db.session.commit()
        assert can_download(owner, f) is False
