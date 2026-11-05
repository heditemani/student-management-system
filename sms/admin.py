"""Administrator-only endpoints: user accounts and the activity log."""

import math

from flask import Blueprint, abort, g, jsonify, request

from . import accounts
from .auth import admin_required

admin = Blueprint("admin", __name__, url_prefix="/api")


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
