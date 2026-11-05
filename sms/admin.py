"""Administrator-only endpoints: user accounts and the activity log."""

import json
import math
from datetime import datetime
from io import BytesIO

from flask import Blueprint, abort, g, jsonify, request, send_file

from . import accounts
from .auth import admin_required
from . import repository as repo
from .validation import validate_student

admin = Blueprint("admin", __name__, url_prefix="/api")
BACKUP_LIMIT = 50_000


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Request body must be a JSON object.")
    return data


def _target(pk):
    row = accounts.get_user(pk)
    if row is None:
        abort(404, description="User not found.")
    return row


@admin.get("/users")
@admin_required
def list_users():
    return jsonify(accounts.list_users())


@admin.post("/users")
@admin_required
def create_user():
    clean, errors = accounts.validate_new_user(_body())
    if errors:
        return jsonify(errors=errors), 400
    try:
        row = accounts.create_user(clean["username"], clean["password"], clean["role"])
    except accounts.DuplicateUser:
        return jsonify(errors={"username": "This username is already taken."}), 400
    accounts.audit("user.create", row["username"], f"role {row['role']}")
    response = jsonify(accounts.public(row))
    response.status_code = 201
    return response


@admin.patch("/users/<int:pk>")
@admin_required
def update_user(pk):
    target, data = _target(pk), _body()
    errors, changed = {}, []

    own = target["id"] == g.user["id"]
    if "role" in data:
        if data["role"] not in accounts.ROLES:
            errors["role"] = "Role must be admin or staff."
        elif own and data["role"] != target["role"]:
            errors["role"] = "You cannot change your own role."
    if "active" in data:
        if not isinstance(data["active"], bool):
            errors["active"] = "Must be true or false."
        elif own and not data["active"]:
            errors["active"] = "You cannot disable your own account."
    if "password" in data:
        problem = accounts.password_problem(data["password"], target["username"])
        if problem:
            errors["password"] = problem
    if errors:
        return jsonify(errors=errors), 400

    if "role" in data and data["role"] != target["role"]:
        accounts.set_role(pk, data["role"])
        changed.append(f"role {data['role']}")
    if "active" in data and data["active"] != bool(target["active"]):
        accounts.set_active(pk, data["active"])
        changed.append("enabled" if data["active"] else "disabled")
    if "password" in data:
        accounts.set_password(pk, data["password"])
        changed.append("password reset")
    if changed:
        accounts.audit("user.update", target["username"], ", ".join(changed))
    return jsonify(accounts.public(accounts.get_user(pk)))


@admin.delete("/users/<int:pk>")
@admin_required
def delete_user(pk):
    target = _target(pk)
    if target["id"] == g.user["id"]:
        abort(400, description="You cannot delete your own account.")
    accounts.delete_user(pk)
    accounts.audit("user.delete", target["username"])
    return "", 204


@admin.get("/audit")
@admin_required
def audit_log():
    try:
        page = max(1, int(request.args.get("page", 1)))
        size = min(100, max(1, int(request.args.get("page_size", 20))))
    except ValueError:
        abort(400, description="page and page_size must be whole numbers.")
    rows, total = accounts.list_audit(page, size)
    return jsonify(count=total, page=page, page_size=size,
                   pages=max(1, math.ceil(total / size)), results=rows)


@admin.get("/backup")
@admin_required
def download_backup():
    payload = json.dumps(repo.backup_data(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    accounts.audit("backup.export", f"{len(payload)} bytes")
    return send_file(
        BytesIO(payload),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"student-management-backup-{datetime.now().date().isoformat()}.json",
    )


def _backup_timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


@admin.post("/backup/restore")
@admin_required
def restore_backup():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        abort(400, description="Choose a backup JSON file.")
    if not upload.filename.lower().endswith(".json"):
        abort(400, description="Choose a file with the .json extension.")
    try:
        payload = json.loads(upload.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        abort(400, description="Backup must be a valid UTF-8 JSON file.")
    if not isinstance(payload, dict) or payload.get("version") != 1:
        abort(400, description="Unsupported backup format.")
    students, history = payload.get("students"), payload.get("history")
    if not isinstance(students, list) or not isinstance(history, list):
        abort(400, description="Backup must contain students and history lists.")
    if len(students) > BACKUP_LIMIT or len(history) > BACKUP_LIMIT * 20:
        abort(400, description=f"Backup exceeds the limit of {BACKUP_LIMIT} students.")

    clean_students, emails, student_ids, student_pks = [], set(), set(), set()
    for index, row in enumerate(students, 1):
        if not isinstance(row, dict):
            abort(400, description=f"Backup student {index} is invalid.")
        clean, errors = validate_student(row, creating=True)
        if errors or not clean.get("student_id"):
            abort(400, description=f"Backup student {index} contains invalid student data.")
        email, student_id = clean["email"].casefold(), clean["student_id"].casefold()
        if email in emails or student_id in student_ids:
            abort(400, description=f"Backup contains duplicate student data at row {index}.")
        student_pk = row.get("id")
        if not isinstance(student_pk, int) or isinstance(student_pk, bool) or student_pk < 1:
            abort(400, description=f"Backup student {index} has an invalid record ID.")
        if student_pk in student_pks:
            abort(400, description=f"Backup contains duplicate record IDs at row {index}.")
        emails.add(email)
        student_ids.add(student_id)
        student_pks.add(student_pk)
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        if not _backup_timestamp(created_at) or not _backup_timestamp(updated_at):
            abort(400, description=f"Backup student {index} has an invalid timestamp.")
        clean_students.append({"id": student_pk, **clean, "created_at": created_at, "updated_at": updated_at})

    clean_history, history_ids = [], set()
    for index, row in enumerate(history, 1):
        if not isinstance(row, dict):
            abort(400, description=f"Backup history item {index} is invalid.")
        history_student_id = row.get("student_id")
        if not isinstance(history_student_id, str):
            abort(400, description=f"Backup history item {index} has an invalid student ID.")
        if row.get("action") not in ("created", "updated", "deleted", "restored"):
            abort(400, description=f"Backup history item {index} has an invalid action.")
        student_pk = row.get("student_pk")
        if not isinstance(student_pk, int) or isinstance(student_pk, bool) or student_pk < 1:
            abort(400, description=f"Backup history item {index} has an invalid record ID.")
        history_pk = row.get("id")
        if not isinstance(history_pk, int) or isinstance(history_pk, bool) or history_pk < 1 or history_pk in history_ids:
            abort(400, description=f"Backup history item {index} has an invalid history ID.")
        history_ids.add(history_pk)
        if not isinstance(row.get("username"), str) or len(row["username"]) > 60:
            abort(400, description=f"Backup history item {index} has an invalid username.")
        if not _backup_timestamp(row.get("at")) or not isinstance(row.get("snapshot"), dict):
            abort(400, description=f"Backup history item {index} is invalid.")
        snapshot, errors = validate_student(row["snapshot"], creating=True)
        if errors or snapshot.get("student_id", "").casefold() != history_student_id.casefold():
            abort(400, description=f"Backup history item {index} contains invalid student data.")
        clean_history.append({
            "id": history_pk,
            "student_pk": student_pk,
            "student_id": history_student_id,
            "action": row["action"],
            "username": row["username"],
            "at": row["at"],
            "snapshot": snapshot,
        })

    repo.restore_data(clean_students, clean_history)
    accounts.audit("backup.restore", f"{len(clean_students)} students")
    return jsonify(restored=len(clean_students), history=len(clean_history))
