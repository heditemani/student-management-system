"""Student Management System: Flask app factory."""

import os
import secrets
from datetime import datetime, timedelta

from flask import Flask, abort, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from . import accounts, db
from .admin import admin
from . import api as api_module
from .api import api
from .auth import auth, current_user, enforce_auth

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def _secret_key(app):
    """SECRET_KEY from the environment, else a random key saved in instance/secret_key."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(app.instance_path, "secret_key")
    os.makedirs(app.instance_path, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    with open(path) as handle:
        return handle.read().strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.environ.get("DATABASE_PATH")
        or os.path.join(app.instance_path, "students.db"),
        JSON_SORT_KEYS=False,
        SESSION_COOKIE_NAME="sms_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _secret_key(app)

    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    db.init_app(app)
    app.register_blueprint(api)
    app.register_blueprint(auth)
    app.register_blueprint(admin)
    app.before_request(enforce_auth)

    @app.get("/")
    def index():
        user = current_user()
        if user is None:
            return render_template("login.html")
        return render_template("index.html", user=accounts.public(user), csrf=session["csrf"])

    @app.get("/reports/print")
    def print_report():
        user = current_user()
        if user is None:
            return redirect("/")
        errors = {}
        filters = api_module._filters(errors)
        if errors:
            abort(400, description="Invalid report filters: " + " ".join(errors.values()))
        rows, total = api_module.repo.list_students(page=1, page_size=10_000, **filters)
        if total > 10_000:
            abort(400, description="Reports are limited to 10,000 matching students. Add filters and try again.")
        return render_template("report.html", students=rows, total=total, filters=filters,
                               generated_at=datetime.now().astimezone())

    @app.errorhandler(HTTPException)
    def http_error(error):
        # The API always answers in JSON; other pages keep Flask's default error page.
        if request.path.startswith("/api/"):
            return jsonify(detail=error.description or error.name), error.code
        return error

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/") or request.path == "/" or request.path.startswith("/reports/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    return app
