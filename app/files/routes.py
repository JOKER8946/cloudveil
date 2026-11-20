"""File REST API (see CLAUDE.md §7)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from ..auth.decorators import (
    csrf_protect,
    get_current_user,
    login_required,
    require_role,
)
from . import service
from .service import FileError

bp = Blueprint("files", __name__, url_prefix="/api/files")


def _err(exc: FileError):
    return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status


@bp.post("")
@require_role("student")
@csrf_protect
def upload():
    user = get_current_user()
    upload_file = request.files.get("file")
    if upload_file is None or not upload_file.filename:
        return (
            jsonify({"error": {"code": "no_file", "message": "No file uploaded."}}),
            400,
        )
    data = upload_file.read()
    category = request.form.get("category", "other")
    try:
        record = service.create_file(user, upload_file.filename, data, category)
    except FileError as exc:
        return _err(exc)
    return jsonify({"file": record.to_dict()}), 201


@bp.get("")
@require_role("student")
def list_my_files():
    user = get_current_user()
    files = service.list_own(user)
    return jsonify({"files": [f.to_dict() for f in files]})


@bp.get("/shared")
@require_role("officer")
def list_shared():
    user = get_current_user()
    files = service.list_shared_with(user)
    return jsonify({"files": [f.to_dict() for f in files]})


@bp.get("/<file_id>")
@login_required
def metadata(file_id: str):
    user = get_current_user()
    try:
        record = service.get_file_or_404(file_id)
    except FileError as exc:
        return _err(exc)
    if not service.can_download(user, record):
        return (
            jsonify({"error": {"code": "forbidden", "message": "Not authorized."}}),
            403,
        )
    return jsonify({"file": record.to_dict()})


@bp.get("/<file_id>/download")
@login_required
def download(file_id: str):
    user = get_current_user()
    try:
        record = service.get_file_or_404(file_id)
        plaintext, record = service.download(user, record)
    except FileError as exc:
        return _err(exc)
    resp = Response(plaintext, mimetype=record.content_type)
    safe_name = record.original_name.replace('"', "")
    resp.headers["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    resp.headers["Content-Length"] = str(len(plaintext))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/<file_id>/share")
@login_required
@csrf_protect
def share(file_id: str):
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    try:
        record = service.get_file_or_404(file_id)
        service.share(
            user, record, data.get("grantee_email", ""), data.get("expires_at")
        )
    except FileError as exc:
        return _err(exc)
    return jsonify({"status": "ok"})


@bp.delete("/<file_id>/share/<int:grantee_id>")
@login_required
@csrf_protect
def revoke(file_id: str, grantee_id: int):
    user = get_current_user()
    try:
        record = service.get_file_or_404(file_id)
        service.revoke(user, record, grantee_id)
    except FileError as exc:
        return _err(exc)
    return jsonify({"status": "ok"})


@bp.delete("/<file_id>")
@login_required
@csrf_protect
def delete(file_id: str):
    user = get_current_user()
    try:
        record = service.get_file_or_404(file_id)
        service.delete_file(user, record)
    except FileError as exc:
        return _err(exc)
    return jsonify({"status": "ok"})
