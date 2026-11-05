"""REST API: /api/students, /api/stats, /api/courses."""

import csv
import io
import math
import re
from datetime import date

from flask import Blueprint, Response, abort, jsonify, request, url_for

from . import accounts
from . import repository as repo
from .auth import admin_required
from .validation import DEFAULTS, STATUSES, validate_student

api = Blueprint("api", __name__, url_prefix="/api")

EXPORT_LIMIT = 10_000
CSV_COLUMNS = (
    "student_id", "first_name", "last_name", "email", "phone", "date_of_birth",
    "gender", "course", "year", "average", "status", "address", "created_at",
)
_NUMBER_LIKE = re.compile(r"^[+-]?[\d\s().-]+$")


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Request body must be a JSON object.")
    return data


def _int_arg(name, default, minimum, maximum, errors):
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        errors[name] = "Must be a whole number."
        return default
    if not minimum <= value <= maximum:
        errors[name] = f"Must be between {minimum} and {maximum}."
        return default
    return value


def _validation_error(errors):
    return jsonify(errors=errors), 400


def _get_or_404(pk):
    student = repo.get_student(pk)
    if student is None:
        abort(404, description="Student not found.")
    return student


def _filters(errors):
    ordering = request.args.get("ordering", repo.DEFAULT_ORDERING)
    if ordering not in repo.ORDERINGS:
        errors["ordering"] = "Invalid ordering."
    status = request.args.get("status", "").strip().lower()
    if status and status not in STATUSES:
        errors["status"] = "Invalid status."
    return {
        "search": request.args.get("search", "").strip()[:100],
        "course": request.args.get("course", "").strip()[:80],
        "status": status,
        "ordering": ordering,
    }


def _csv_cell(value):
    """Neutralise spreadsheet formulas (CSV injection) in text that starts with = + - @."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in "=+-@\t\r" and not _NUMBER_LIKE.match(text):
        return "'" + text
    return text


@api.get("/students/export.csv")
def export_students():
    errors = {}
    filters = _filters(errors)
    if errors:
        return _validation_error(errors)
    rows, _total = repo.list_students(page=1, page_size=EXPORT_LIMIT, **filters)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow([_csv_cell(row.get(column)) for column in CSV_COLUMNS])
    accounts.audit("students.export", f"{len(rows)} rows")

    filename = f"students-{date.today().isoformat()}.csv"
    response = Response(
        "\ufeff" + buffer.getvalue(),  # BOM so Excel reads accents correctly
        mimetype="text/csv",
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api.get("/students")
def list_students():
    errors = {}
    page = _int_arg("page", 1, 1, 1_000_000, errors)
    page_size = _int_arg("page_size", 10, 1, 100, errors)
    filters = _filters(errors)
    if errors:
        return _validation_error(errors)

    results, total = repo.list_students(page=page, page_size=page_size, **filters)
    return jsonify(
        count=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
        results=results,
    )


@api.post("/students")
def create_student():
    clean, errors = validate_student(_json_body(), creating=True)
    if errors:
        return _validation_error(errors)
    try:
        student = repo.create_student(clean)
    except repo.DuplicateError as error:
        return _validation_error({error.field: error.message})
    accounts.audit("student.create", student["student_id"], student["full_name"])
    response = jsonify(student)
    response.status_code = 201
    response.headers["Location"] = url_for("api.get_student", pk=student["id"])
    return response


@api.get("/students/<int:pk>")
def get_student(pk):
    return jsonify(_get_or_404(pk))


def _update(pk, partial):
    before = _get_or_404(pk)
    clean, errors = validate_student(_json_body(), partial=partial)
    if errors:
        return _validation_error(errors)
    if not partial:
        # PUT replaces the record: optional fields that were left out go back to defaults.
        clean = {**DEFAULTS, **clean}
    try:
        after = repo.update_student(pk, clean)
    except repo.DuplicateError as error:
        return _validation_error({error.field: error.message})
    changed = [f for f in repo.FIELDS if before.get(f) != after.get(f)]
    accounts.audit("student.update", after["student_id"], ", ".join(changed) or "no changes")
    return jsonify(after)


@api.put("/students/<int:pk>")
def replace_student(pk):
    return _update(pk, partial=False)


@api.patch("/students/<int:pk>")
def patch_student(pk):
    return _update(pk, partial=True)


@api.delete("/students/<int:pk>")
@admin_required
def delete_student(pk):
    student = _get_or_404(pk)
    repo.delete_student(pk)
    accounts.audit("student.delete", student["student_id"], student["full_name"])
    return "", 204


@api.get("/stats")
def stats():
    return jsonify(repo.stats())


@api.get("/courses")
def courses():
    return jsonify(repo.courses())
