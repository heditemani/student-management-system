"""Sessions, login, roles and CSRF protection.

Every /api/ request except POST /api/auth/login needs a signed-in user. Requests that
change data also need the X-CSRF-Token header (the token is in the session).
"""

import hmac
import secrets
import time
from functools import wraps

from flask import Blueprint, abort, g, jsonify, request, session

from . import accounts

auth = Blueprint("auth", __name__, url_prefix="/api/auth")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MAX_PER_ACCOUNT = 5      # failed logins per IP + username
MAX_PER_IP = 20          # failed logins per IP, any username
WINDOW_SECONDS = 15 * 60


# ---------- login throttling (in memory: per process, reset on restart) ----------

def _failures():
    from flask import current_app
    return current_app.extensions.setdefault("login_failures", {})


def _keys(username):
    ip = request.remote_addr or "?"
    return (("ip", ip), ("acct", ip, username.lower()))


def _wait_seconds(username):
    """Seconds the caller must wait, or 0 if login attempts are allowed."""
    store, now, wait = _failures(), time.time(), 0
    for key, limit in zip(_keys(username), (MAX_PER_IP, MAX_PER_ACCOUNT)):
        entry = store.get(key)
        if not entry:
            continue
        count, first = entry
        if now - first >= WINDOW_SECONDS:
            store.pop(key, None)
        elif count >= limit:
            wait = max(wait, int(WINDOW_SECONDS - (now - first)) + 1)
    return wait


def _record_failure(username):
    store, now = _failures(), time.time()
    if len(store) > 10_000:
        for key in [k for k, (_, first) in store.items() if now - first >= WINDOW_SECONDS]:
            store.pop(key, None)
    for key in _keys(username):
        count, first = store.get(key, (0, now))
        if now - first >= WINDOW_SECONDS:
            count, first = 0, now
        store[key] = (count + 1, first)


def _clear_failures(username):
    _failures().pop(_keys(username)[1], None)


# ---------- current user ----------

def current_user():
    uid = session.get("uid")
    if uid is None:
        return None
    row = accounts.get_user(uid)
    if row is None or not row["active"] or row["token_version"] != session.get("tv"):
        session.clear()
        return None
    return row


def start_session(row):
    session.clear()  # new session on every login (prevents fixation)
    session["uid"] = row["id"]
    session["tv"] = row["token_version"]
    session["csrf"] = secrets.token_urlsafe(32)
    session.permanent = True


def enforce_auth():
    """Runs before every request. Sets g.user for authenticated API calls."""
    g.user = None
    if not request.path.startswith("/api/"):
        return None
    if request.endpoint == "auth.login":
        return None
    user = current_user()
    if user is None:
        abort(401, description="Sign in required.")
    g.user = user
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("X-CSRF-Token", "")
        if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
            abort(403, description="Missing or invalid CSRF token. Reload the page.")
    return None


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None or g.user["role"] != "admin":
            abort(403, description="Administrator access required.")
        return view(*args, **kwargs)
    return wrapper


def session_payload(row):
    return {**accounts.public(row), "csrf": session.get("csrf", "")}


# ---------- endpoints ----------

@auth.post("/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Request body must be a JSON object.")
    username = str(data.get("username", "")).strip()[:60]
    password = data.get("password")

    wait = _wait_seconds(username)
    if wait:
        minutes = max(1, round(wait / 60))
        response = jsonify(detail=f"Too many failed attempts. Try again in about {minutes} minute(s).")
        response.status_code = 429
        response.headers["Retry-After"] = str(wait)
        return response

    row = accounts.get_by_username(username) if username else None
    ok = accounts.check_password(row, password)
    if not ok or not row["active"]:
        _record_failure(username)
        accounts.audit("login.failed", username, "", username=username[:60])
        abort(401, description="Invalid username or password.")

    _clear_failures(username)
    accounts.touch_login(row["id"])
    start_session(row)
    g.user = row
    accounts.audit("login", row["username"])
    return jsonify(session_payload(accounts.get_user(row["id"])))


@auth.post("/logout")
def logout():
    accounts.audit("logout", g.user["username"])
    session.clear()
    return "", 204


@auth.get("/me")
def me():
    return jsonify(session_payload(g.user))


@auth.post("/password")
def change_password():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Request body must be a JSON object.")
    if not accounts.check_password(g.user, data.get("current_password")):
        return jsonify(errors={"current_password": "Current password is incorrect."}), 400
    new = data.get("new_password")
    problem = accounts.password_problem(new, g.user["username"])
    if problem:
        return jsonify(errors={"new_password": problem}), 400
    if new == data.get("current_password"):
        return jsonify(errors={"new_password": "Choose a different password."}), 400
    row = accounts.set_password(g.user["id"], new)
    session["tv"] = row["token_version"]  # keep this session, drop the others
    accounts.audit("password.change", row["username"])
    return "", 204
