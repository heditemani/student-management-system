"""All database access for students. Every query is parameterised."""

import sqlite3
from datetime import date

from .db import get_db
from .validation import DEFAULTS

FIELDS = (
    "student_id", "first_name", "last_name", "email", "phone", "date_of_birth",
    "gender", "course", "year", "average", "status", "address",
)

# Whitelist: the ?ordering= value is mapped to SQL here, never interpolated.
ORDERINGS = {
    "name": "last_name COLLATE NOCASE ASC, first_name COLLATE NOCASE ASC, id ASC",
    "-name": "last_name COLLATE NOCASE DESC, first_name COLLATE NOCASE DESC, id DESC",
    "student_id": "student_id ASC",
    "-student_id": "student_id DESC",
    "course": "course COLLATE NOCASE ASC, last_name COLLATE NOCASE ASC, id ASC",
    "-course": "course COLLATE NOCASE DESC, last_name COLLATE NOCASE ASC, id ASC",
    "year": "year ASC, last_name COLLATE NOCASE ASC, id ASC",
    "-year": "year DESC, last_name COLLATE NOCASE ASC, id ASC",
    "average": "average IS NULL, average ASC, id ASC",
    "-average": "average IS NULL, average DESC, id ASC",
    "created": "id ASC",
    "-created": "id DESC",
}
DEFAULT_ORDERING = "-created"

DUPLICATE_MESSAGES = {
    "email": "A student with this email already exists.",
    "student_id": "This student ID is already in use.",
}


class DuplicateError(Exception):
    def __init__(self, field):
        super().__init__(field)
        self.field = field
        self.message = DUPLICATE_MESSAGES[field]


def to_dict(row):
    student = dict(row)
    student["full_name"] = f"{student['first_name']} {student['last_name']}"
    return student


def _like(term):
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_students(search="", course="", status="", ordering=DEFAULT_ORDERING, page=1, page_size=10):
    db = get_db()
    where, params = [], []

    if search:
        like = _like(search)
        where.append(
            "(first_name LIKE ? ESCAPE '\\' OR last_name LIKE ? ESCAPE '\\' "
            "OR (first_name || ' ' || last_name) LIKE ? ESCAPE '\\' "
            "OR email LIKE ? ESCAPE '\\' OR student_id LIKE ? ESCAPE '\\' "
            "OR course LIKE ? ESCAPE '\\')"
        )
        params += [like] * 6
    if course:
        where.append("course = ? COLLATE NOCASE")
        params.append(course)
    if status:
        where.append("status = ?")
        params.append(status)

    clause = f" WHERE {' AND '.join(where)}" if where else ""
    total = db.execute(f"SELECT COUNT(*) FROM students{clause}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM students{clause} ORDER BY {ORDERINGS[ordering]} LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    return [to_dict(r) for r in rows], total


def get_student(pk):
    row = get_db().execute("SELECT * FROM students WHERE id = ?", (pk,)).fetchone()
    return to_dict(row) if row else None


def _next_student_id(db):
    prefix = f"STU-{date.today().year}-"
    row = db.execute(
        "SELECT student_id FROM students WHERE student_id LIKE ? ORDER BY student_id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    last = 0
    if row:
        tail = row[0][len(prefix):]
        last = int(tail) if tail.isdigit() else 0
    return f"{prefix}{last + 1:04d}"


def _ensure_unique(db, data, exclude_id=None):
    for field in ("email", "student_id"):
        if field not in data:
            continue
        sql = f"SELECT 1 FROM students WHERE {field} = ? COLLATE NOCASE"
        args = [data[field]]
        if exclude_id is not None:
            sql += " AND id != ?"
            args.append(exclude_id)
        if db.execute(sql, args).fetchone():
            raise DuplicateError(field)


def _duplicate_from_integrity_error(error):
    text = str(error)
    if "students.email" in text:
        return DuplicateError("email")
    if "students.student_id" in text:
        return DuplicateError("student_id")
    return None


def create_student(data):
    db = get_db()
    values = {**DEFAULTS, **data}
    auto_id = "student_id" not in values
    _ensure_unique(db, values)

    for _attempt in range(5):
        if auto_id:
            values["student_id"] = _next_student_id(db)
        columns = [f for f in FIELDS if f in values]
        try:
            cur = db.execute(
                f"INSERT INTO students ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                [values[c] for c in columns],
            )
            db.commit()
            return get_student(cur.lastrowid)
        except sqlite3.IntegrityError as error:
            db.rollback()
            duplicate = _duplicate_from_integrity_error(error)
            if auto_id and duplicate and duplicate.field == "student_id":
                continue  # another request took this number; try the next one
            if duplicate:
                raise duplicate from error
            raise
    raise RuntimeError("Could not generate a unique student ID.")


def update_student(pk, data):
    db = get_db()
    _ensure_unique(db, data, exclude_id=pk)
    columns = [f for f in FIELDS if f in data]
    if not columns:
        return get_student(pk)
    assignments = ", ".join(f"{c} = ?" for c in columns)
    try:
        db.execute(
            f"UPDATE students SET {assignments}, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
            [data[c] for c in columns] + [pk],
        )
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        duplicate = _duplicate_from_integrity_error(error)
        if duplicate:
            raise duplicate from error
        raise
    return get_student(pk)


def delete_student(pk):
    db = get_db()
    cur = db.execute("DELETE FROM students WHERE id = ?", (pk,))
    db.commit()
    return cur.rowcount > 0


def stats():
    row = get_db().execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(status = 'active'), 0) AS active, "
        "COALESCE(SUM(status = 'graduated'), 0) AS graduated, "
        "COALESCE(SUM(status = 'suspended'), 0) AS suspended, "
        "ROUND(AVG(average), 2) AS average, "
        "COUNT(DISTINCT course) AS courses FROM students"
    ).fetchone()
    result = dict(row)
    result["by_course"] = [
        {"course": r["course"], "count": r["count"]}
        for r in get_db().execute(
            "SELECT course, COUNT(*) AS count FROM students "
            "GROUP BY course COLLATE NOCASE ORDER BY count DESC, course COLLATE NOCASE"
        )
    ]
    return result


def courses():
    rows = get_db().execute(
        "SELECT DISTINCT course FROM students ORDER BY course COLLATE NOCASE"
    ).fetchall()
    return [r[0] for r in rows]
