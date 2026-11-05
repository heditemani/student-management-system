"""All database access for students. Every query is parameterised."""

import json
import sqlite3
from datetime import date

from .db import get_db
from .validation import DEFAULTS

FIELDS = (
    "student_id", "first_name", "last_name", "email", "phone", "date_of_birth",
    "gender", "course", "year", "academic_year", "semester", "average", "status", "address",
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


def list_students(search="", course="", status="", ordering=DEFAULT_ORDERING, page=1, page_size=10,
                  average_min=None, average_max=None, missing_average=False, year_min=None,
                  year_max=None, academic_year="", semester=None, created_from="", created_to=""):
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
    if average_min is not None:
        where.append("average >= ?")
        params.append(average_min)
    if average_max is not None:
        where.append("average <= ?")
        params.append(average_max)
    if missing_average:
        where.append("average IS NULL")
    if year_min is not None:
        where.append("year >= ?")
        params.append(year_min)
    if year_max is not None:
        where.append("year <= ?")
        params.append(year_max)
    if academic_year:
        where.append("academic_year = ?")
        params.append(academic_year)
    if semester is not None:
        where.append("semester = ?")
        params.append(semester)
    if created_from:
        where.append("date(created_at) >= date(?)")
        params.append(created_from)
    if created_to:
        where.append("date(created_at) <= date(?)")
        params.append(created_to)

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


def _record_history(db, student, action, username=""):
    snapshot = {field: student.get(field) for field in FIELDS}
    db.execute(
        "INSERT INTO student_history (student_pk, student_id, action, username, snapshot) "
        "VALUES (?, ?, ?, ?, ?)",
        (student["id"], student["student_id"], action, username[:60],
         json.dumps(snapshot, ensure_ascii=False)),
    )


def create_student(data, username=""):
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
            student = get_student(cur.lastrowid)
            _record_history(db, student, "created", username)
            db.commit()
            return student
        except sqlite3.IntegrityError as error:
            db.rollback()
            duplicate = _duplicate_from_integrity_error(error)
            if auto_id and duplicate and duplicate.field == "student_id":
                continue  # another request took this number; try the next one
            if duplicate:
                raise duplicate from error
            raise
    raise RuntimeError("Could not generate a unique student ID.")


def update_student(pk, data, username=""):
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
        student = get_student(pk)
        _record_history(db, student, "updated", username)
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        duplicate = _duplicate_from_integrity_error(error)
        if duplicate:
            raise duplicate from error
        raise
    return get_student(pk)


def delete_student(pk, username=""):
    db = get_db()
    student = get_student(pk)
    if student is None:
        return False
    _record_history(db, student, "deleted", username)
    cur = db.execute("DELETE FROM students WHERE id = ?", (pk,))
    db.commit()
    return cur.rowcount > 0


def student_history(student_pk):
    rows = get_db().execute(
        "SELECT id, at, username, action, snapshot FROM student_history "
        "WHERE student_pk = ? ORDER BY id DESC LIMIT 100",
        (student_pk,),
    ).fetchall()
    return [
        {**dict(row), "snapshot": json.loads(row["snapshot"])}
        for row in rows
    ]


def duplicate_field(data):
    try:
        _ensure_unique(get_db(), data)
    except DuplicateError as error:
        return error.field
    return None


def alerts():
    db = get_db()
    return dict(db.execute(
        "SELECT SUM(CASE WHEN average IS NOT NULL AND average < 10 THEN 1 ELSE 0 END) AS low_average, "
        "SUM(CASE WHEN average IS NULL THEN 1 ELSE 0 END) AS missing_average FROM students"
    ).fetchone())


def import_students(records, username=""):
    db = get_db()
    inserted, duplicates = [], []
    try:
        db.execute("BEGIN")
        for row_number, data in records:
            try:
                _ensure_unique(db, data)
            except DuplicateError as error:
                duplicates.append({"row": row_number, "field": error.field, "message": error.message})
                continue
            values = {**DEFAULTS, **data}
            auto_id = not values.get("student_id")
            for _attempt in range(5):
                if auto_id:
                    values["student_id"] = _next_student_id(db)
                columns = [field for field in FIELDS if field in values]
                try:
                    cur = db.execute(
                        f"INSERT INTO students ({', '.join(columns)}) "
                        f"VALUES ({', '.join('?' for _ in columns)})",
                        [values[field] for field in columns],
                    )
                    student = get_student(cur.lastrowid)
                    _record_history(db, student, "created", username)
                    inserted.append(student["id"])
                    break
                except sqlite3.IntegrityError as error:
                    duplicate = _duplicate_from_integrity_error(error)
                    if auto_id and duplicate and duplicate.field == "student_id":
                        continue
                    if duplicate:
                        duplicates.append({"row": row_number, "field": duplicate.field,
                                           "message": duplicate.message})
                        break
                    raise
            else:
                raise RuntimeError("Could not generate a unique student ID.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"created": len(inserted), "duplicates": duplicates}


def backup_data():
    db = get_db()
    students = [dict(row) for row in db.execute("SELECT * FROM students ORDER BY id")]
    history = [
        {**dict(row), "snapshot": json.loads(row["snapshot"])}
        for row in db.execute("SELECT * FROM student_history ORDER BY id")
    ]
    return {"version": 1, "students": students, "history": history}


def restore_data(students, history):
    db = get_db()
    try:
        db.execute("BEGIN")
        db.execute("DELETE FROM student_history")
        db.execute("DELETE FROM students")
        for student in students:
            columns = ["id"] + [field for field in FIELDS if field in student]
            columns.extend(("created_at", "updated_at"))
            db.execute(
                f"INSERT INTO students ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                [student[field] for field in columns],
            )
        for row in history:
            db.execute(
                "INSERT INTO student_history (id, student_pk, student_id, action, username, at, snapshot) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row["id"], row["student_pk"], row["student_id"], row["action"], row["username"], row["at"],
                 json.dumps(row["snapshot"], ensure_ascii=False)),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise


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
