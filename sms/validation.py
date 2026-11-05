"""Input validation for student records.

validate_student() returns (clean, errors). `errors` maps a field name to a
human-readable message; an empty dict means the data is valid.
"""

import math
import re
from datetime import date

STATUSES = ("active", "graduated", "suspended")
GENDERS = ("", "female", "male", "other")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[\d\s().-]{6,20}$")
STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9-]{3,20}$")

# (field, required, max length)
TEXT_FIELDS = (
    ("first_name", True, 60),
    ("last_name", True, 60),
    ("course", True, 80),
    ("phone", False, 20),
    ("address", False, 200),
)

DEFAULTS = {
    "phone": "",
    "date_of_birth": None,
    "gender": "",
    "year": 1,
    "average": None,
    "status": "active",
    "address": "",
}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_student(data, partial=False, creating=False):
    clean, errors = {}, {}

    def wanted(key):
        return not partial or key in data

    for key, required, max_len in TEXT_FIELDS:
        if not wanted(key):
            continue
        value = data.get(key)
        if value is None:
            value = ""
        if not isinstance(value, str):
            errors[key] = "Must be text."
            continue
        value = value.strip()
        if required and not value:
            errors[key] = "This field is required."
        elif len(value) > max_len:
            errors[key] = f"Must be at most {max_len} characters."
        elif key == "course" and len(value) < 2:
            errors[key] = "Must be at least 2 characters."
        elif key == "phone" and value and not PHONE_RE.match(value):
            errors[key] = "Enter a valid phone number."
        else:
            clean[key] = value

    if wanted("email"):
        value = data.get("email")
        if not isinstance(value, str) or not value.strip():
            errors["email"] = "This field is required."
        else:
            value = value.strip().lower()
            if len(value) > 254 or not EMAIL_RE.match(value):
                errors["email"] = "Enter a valid email address."
            else:
                clean["email"] = value

    if "student_id" in data:
        value = data.get("student_id")
        if value is None or (isinstance(value, str) and not value.strip()):
            if not creating:
                errors["student_id"] = "This field cannot be blank."
        elif not isinstance(value, str):
            errors["student_id"] = "Must be text."
        else:
            value = value.strip().upper()
            if STUDENT_ID_RE.match(value):
                clean["student_id"] = value
            else:
                errors["student_id"] = "Use 3 to 20 letters, digits or dashes."

    if wanted("date_of_birth"):
        value = data.get("date_of_birth")
        if value in (None, ""):
            clean["date_of_birth"] = None
        elif not isinstance(value, str):
            errors["date_of_birth"] = "Use the format YYYY-MM-DD."
        else:
            try:
                parsed = date.fromisoformat(value.strip())
            except ValueError:
                errors["date_of_birth"] = "Use a valid date (YYYY-MM-DD)."
            else:
                if parsed < date(1900, 1, 1) or parsed > date.today():
                    errors["date_of_birth"] = "Date of birth is out of range."
                else:
                    clean["date_of_birth"] = parsed.isoformat()

    if wanted("gender"):
        value = data.get("gender")
        value = "" if value is None else value
        if not isinstance(value, str) or value.strip().lower() not in GENDERS:
            errors["gender"] = "Choose female, male or other."
        else:
            clean["gender"] = value.strip().lower()

    if wanted("year"):
        value = data.get("year")
        if value in (None, ""):
            value = DEFAULTS["year"]
        if isinstance(value, str) and re.fullmatch(r"\d{1,2}", value.strip()):
            value = int(value)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 6:
            errors["year"] = "Year must be a whole number from 1 to 6."
        else:
            clean["year"] = value

    if wanted("average"):
        value = data.get("average")
        if value in (None, ""):
            clean["average"] = None
        else:
            if isinstance(value, str):
                try:
                    value = float(value.strip().replace(",", "."))
                except ValueError:
                    value = None
            if not _is_number(value) or not math.isfinite(value) or not 0 <= value <= 20:
                errors["average"] = "Average must be a number from 0 to 20."
            else:
                clean["average"] = round(float(value), 2)

    if wanted("status"):
        value = data.get("status")
        value = "active" if value in (None, "") else value
        if not isinstance(value, str) or value.strip().lower() not in STATUSES:
            errors["status"] = "Choose active, graduated or suspended."
        else:
            clean["status"] = value.strip().lower()

    return clean, errors
