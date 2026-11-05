"""User accounts, password rules and the audit log. Every query is parameterised."""

import re
import sqlite3

from flask import g, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

ROLES = ("admin", "staff")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
AUDIT_KEEP = 5000

# Checked when the username does not exist, so a failed login takes about as long either way.
DUMMY_HASH = generate_password_hash("not-a-real-password-0")


class DuplicateUser(Exception):
    pass


def password_problem(password, username=""):
    """Return a message if the password is not acceptable, else None."""
    if not isinstance(password, str) or not password:
        return "Password is required."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password must be at most 128 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Use at least one letter and one number."
    if username and password.lower() == username.lower():
        return "Password must differ from the username."
    return None


def public(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "last_login": row["last_login"],
    }


def validate_new_user(data):
    errors, clean = {}, {}
    username = str(data.get("username", "")).strip()
    if not USERNAME_RE.match(username):
        errors["username"] = "3 to 30 characters: letters, numbers, dot, dash or underscore."
    clean["username"] = username
    problem = password_problem(data.get("password"), username)
    if problem:
        errors["password"] = problem
    else:
        clean["password"] = data["password"]
    role = data.get("role", "staff")
    if role not in ROLES:
        errors["role"] = "Role must be admin or staff."
    clean["role"] = role
    return clean, errors


def get_user(pk):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (pk,)).fetchone()


def get_by_username(username):
    return get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def list_users():
    rows = get_db().execute("SELECT * FROM users ORDER BY username COLLATE NOCASE").fetchall()
    return [public(r) for r in rows]


def count_users():
    return get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]


def create_user(username, password, role="staff"):
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
        )
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        if "users.username" in str(error):
            raise DuplicateUser(username) from error
        raise
    return get_user(cur.lastrowid)


def check_password(row, password):
    """Verify a password. Pass row=None for unknown users to keep timing similar."""
    stored = row["password_hash"] if row else DUMMY_HASH
    ok = check_password_hash(stored, password if isinstance(password, str) else "")
    return bool(ok and row)


def set_password(pk, password):
    """Change the password and invalidate every other session of that user."""
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
        (generate_password_hash(password), pk),
    )
    db.commit()
    return get_user(pk)


def set_role(pk, role):
    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, pk))
    db.commit()


def set_active(pk, active):
    db = get_db()
    # Disabling also bumps token_version so existing sessions stop working at once.
    db.execute(
        "UPDATE users SET active = ?, token_version = token_version + ? WHERE id = ?",
        (1 if active else 0, 0 if active else 1, pk),
    )
    db.commit()


def delete_user(pk):
    db = get_db()
    cur = db.execute("DELETE FROM users WHERE id = ?", (pk,))
    db.commit()
    return cur.rowcount > 0


def touch_login(pk):
    db = get_db()
    db.execute("UPDATE users SET last_login = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?", (pk,))
    db.commit()


# ---------- audit log ----------

def audit(action, target="", detail="", username=None):
    if username is None:
        user = g.get("user") if has_request_context() else None
        username = user["username"] if user else ""
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (username, action, target, detail) VALUES (?, ?, ?, ?)",
        (username[:60], action, str(target)[:80], str(detail)[:200]),
    )
    db.execute(
        "DELETE FROM audit_log WHERE id <= (SELECT MAX(id) FROM audit_log) - ?", (AUDIT_KEEP,)
    )
    db.commit()


def list_audit(page=1, page_size=20):
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    rows = db.execute(
        "SELECT id, at, username, action, target, detail FROM audit_log "
        "ORDER BY id DESC LIMIT ? OFFSET ?",
        (page_size, (page - 1) * page_size),
    ).fetchall()
    return [dict(r) for r in rows], total
