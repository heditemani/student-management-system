"""SQLite connection handling and schema."""

import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT    NOT NULL UNIQUE,
    first_name    TEXT    NOT NULL,
    last_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    phone         TEXT    NOT NULL DEFAULT '',
    date_of_birth TEXT,
    gender        TEXT    NOT NULL DEFAULT '' CHECK (gender IN ('', 'female', 'male', 'other')),
    course        TEXT    NOT NULL,
    year          INTEGER NOT NULL DEFAULT 1 CHECK (year BETWEEN 1 AND 6),
    academic_year TEXT    NOT NULL DEFAULT '',
    semester      INTEGER CHECK (semester IS NULL OR semester IN (1, 2)),
    average       REAL    CHECK (average IS NULL OR (average >= 0 AND average <= 20)),
    status        TEXT    NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'graduated', 'suspended')),
    address       TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_students_course ON students (course);
CREATE INDEX IF NOT EXISTS idx_students_status ON students (status);

CREATE TABLE IF NOT EXISTS student_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT    NOT NULL,
    action     TEXT    NOT NULL CHECK (action IN ('created', 'updated', 'deleted', 'restored')),
    username   TEXT    NOT NULL DEFAULT '',
    at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    snapshot   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_student_history_student ON student_history (student_id, id DESC);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'staff' CHECK (role IN ('admin', 'staff')),
    active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    username TEXT NOT NULL DEFAULT '',
    action   TEXT NOT NULL,
    target   TEXT NOT NULL DEFAULT '',
    detail   TEXT NOT NULL DEFAULT ''
);
"""


def get_db():
    """Return the SQLite connection for the current request, opening it if needed."""
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    """Create the tables if they do not exist yet. Safe to call repeatedly."""
    conn = get_db()
    conn.executescript(SCHEMA)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(students)")}
    if "academic_year" not in columns:
        conn.execute("ALTER TABLE students ADD COLUMN academic_year TEXT NOT NULL DEFAULT ''")
    if "semester" not in columns:
        conn.execute("ALTER TABLE students ADD COLUMN semester INTEGER")
    conn.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
