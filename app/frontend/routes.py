"""Frontend page routes. These only render templates; all data flows through the
JSON API via fetch() in the browser (the JWT travels in an HttpOnly cookie)."""

from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("frontend", __name__)


@bp.get("/")
def index():
    return render_template("login.html")


@bp.get("/app")
def dashboard():
    return render_template("dashboard.html")


@bp.get("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")
