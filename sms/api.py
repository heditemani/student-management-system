"""REST API: /api/students, /api/stats, /api/courses."""

import csv
import io
import math
import re
from datetime import date

from werkzeug.exceptions import BadRequest

from flask import Blueprint, Response, abort, g, jsonify, request, url_for

from . import accounts
from . import repository as repo
from .auth import admin_required
from .validation import DEFAULTS, STATUSES, validate_student

api = Blueprint("api", __name__, url_prefix="/api")

EXPORT_LIMIT = 10_000
CSV_COLUMNS = (
    "student_id", "first_name", "last_name", "email", "phone", "date_of_birth",
    "gender", "course", "year", "academic_year", "semester", "average", "status", "address", "created_at",
)
_NUMBER_LIKE = re.compile(r"^[+-]?[\d\s().-]+$")
IMPORT_COLUMNS = set(repo.FIELDS)
IMPORT_LIMIT = 10_000


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
    result = {
        "search": request.args.get("search", "").strip()[:100],
        "course": request.args.get("course", "").strip()[:80],
        "status": status,
        "ordering": ordering,
    }
    for key in ("average_min", "average_max"):
        raw = request.args.get(key, "").strip()
        if raw:
            try:
                value = float(raw)
            except ValueError:
                errors[key] = "Must be a number from 0 to 20."
                continue
            if not math.isfinite(value) or not 0 <= value <= 20:
                errors[key] = "Must be a number from 0 to 20."
            else:
                result[key] = value
    if result.get("average_min") is not None and result.get("average_max") is not None:
        if result["average_min"] > result["average_max"]:
            errors["average_min"] = "Minimum average cannot exceed maximum average."
    for key in ("year_min", "year_max"):
        if request.args.get(key):
            result[key] = _int_arg(key, None, 1, 6, errors)
    if result.get("year_min") is not None and result.get("year_max") is not None:
        if result["year_min"] > result["year_max"]:
            errors["year_min"] = "Minimum year cannot exceed maximum year."
    academic_year = request.args.get("academic_year", "").strip()
    if academic_year:
        clean, year_errors = validate_student({"academic_year": academic_year}, partial=True)
        if "academic_year" in year_errors:
            errors["academic_year"] = year_errors["academic_year"]
        else:
            result["academic_year"] = clean["academic_year"]
    semester = request.args.get("semester", "").strip()
    if semester:
        if semester not in ("1", "2"):
            errors["semester"] = "Semester must be 1 or 2."
        else:
            result["semester"] = int(semester)
    missing_average = request.args.get("missing_average", "").strip().lower()
    if missing_average and missing_average not in ("1", "true", "0", "false"):
        errors["missing_average"] = "Must be true or false."
    result["missing_average"] = missing_average in ("1", "true")
    for key in ("created_from", "created_to"):
        raw = request.args.get(key, "").strip()
        if raw:
            try:
                result[key] = date.fromisoformat(raw).isoformat()
            except ValueError:
                errors[key] = "Use the format YYYY-MM-DD."
    if result.get("created_from") and result.get("created_to"):
        if result["created_from"] > result["created_to"]:
            errors["created_from"] = "Start date cannot be after end date."
    return result


def _read_import():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        abort(400, description="Choose a CSV file to import.")
    if not upload.filename.lower().endswith(".csv"):
        abort(400, description="Choose a file with the .csv extension.")
    try:
        content = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise BadRequest("CSV file must use UTF-8 encoding.") from error
    reader = csv.DictReader(io.StringIO(content, newline=""))
    if not reader.fieldnames:
        abort(400, description="CSV file must include a header row.")
    headers = [header.strip().lower() for header in reader.fieldnames if header]
    required = {"first_name", "last_name", "email", "course"}
    if not required.issubset(headers):
        abort(400, description="CSV headers must include first_name, last_name, email and course.")
    if not set(headers).intersection(IMPORT_COLUMNS):
        abort(400, description="CSV file does not contain supported student fields.")

    records, errors, duplicates, seen = [], [], [], {"email": set(), "student_id": set()}
    try:
        for row_number, raw in enumerate(reader, 2):
            if row_number > IMPORT_LIMIT + 1:
                abort(400, description=f"CSV import is limited to {IMPORT_LIMIT} rows.")
            data = {(key or "").strip().lower(): (value or "").strip()
                    for key, value in raw.items() if key and key.strip().lower() in IMPORT_COLUMNS}
            clean, field_errors = validate_student(data, creating=True)
            if field_errors:
                errors.append({"row": row_number, "errors": field_errors})
                continue
            duplicate = repo.duplicate_field(clean)
            if not duplicate:
                for field in ("email", "student_id"):
                    value = clean.get(field)
                    if value:
                        normalized = value.casefold()
                        if normalized in seen[field]:
                            duplicate = field
                            break
            if duplicate:
                seen_value = clean.get(duplicate, "")
                duplicates.append({"row": row_number, "field": duplicate,
                                   "message": f"Duplicate {duplicate.replace('_', ' ')}: {seen_value}."})
                continue
            for field in ("email", "student_id"):
                if clean.get(field):
                    seen[field].add(clean[field].casefold())
            records.append((row_number, clean))
    except csv.Error as error:
        abort(400, description=f"Invalid CSV file: {error}")
    return records, errors, duplicates


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


@api.post("/students/import/preview")
def preview_student_import():
    records, errors, duplicates = _read_import()
    sample = []
    for row_number, record in records[:10]:
        sample.append({
            "row": row_number,
            "student_id": record.get("student_id") or "Generated on import",
            "name": record["first_name"] + " " + record["last_name"],
            "email": record["email"],
            "course": record["course"],
            "academic_year": record.get("academic_year") or "",
            "semester": record.get("semester"),
        })
    return jsonify(valid=len(records), duplicates=duplicates, errors=errors,
                   total=len(records) + len(duplicates) + len(errors), sample=sample)


@api.post("/students/import")
def import_students():
    records, errors, duplicates = _read_import()
    result = repo.import_students(records, g.user["username"])
    duplicates.extend(result["duplicates"])
    accounts.audit("students.import", f"{result['created']} rows",
                   f"{len(duplicates)} duplicates; {len(errors)} invalid")
    return jsonify(created=result["created"], duplicates=duplicates, errors=errors)


@api.post("/students")
def create_student():
    clean, errors = validate_student(_json_body(), creating=True)
    if errors:
        return _validation_error(errors)
    try:
        student = repo.create_student(clean, g.user["username"])
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


@api.get("/students/<int:pk>/history")
def get_student_history(pk):
    _get_or_404(pk)
    return jsonify(repo.student_history(pk))


def _update(pk, partial):
    before = _get_or_404(pk)
    clean, errors = validate_student(_json_body(), partial=partial)
    if errors:
        return _validation_error(errors)
    if not partial:
        # PUT replaces the record: optional fields that were left out go back to defaults.
        clean = {**DEFAULTS, **clean}
    try:
        after = repo.update_student(pk, clean, g.user["username"])
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
    repo.delete_student(pk, g.user["username"])
    accounts.audit("student.delete", student["student_id"], student["full_name"])
    return "", 204


@api.get("/stats")
def stats():
    return jsonify(repo.stats())


@api.get("/alerts")
def student_alerts():
    return jsonify(repo.alerts())


@api.get("/courses")
def courses():
    return jsonify(repo.courses())
