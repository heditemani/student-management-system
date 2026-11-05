"""Fill the database with demo students.

    python seed.py            add demo data only if the table is empty
    python seed.py --reset    delete every student first, then add demo data
    python seed.py --demo-users   also create accounts "admin" and "staff" with random
                                  passwords (printed once). Skips names that already exist.

All names, emails and phone numbers below are made up.
"""

import secrets
import sys

from sms import accounts, create_app, repository as repo
from sms.db import get_db
from sms.validation import validate_student

DEMO_STUDENTS = [
    ("Amira", "Ben Salah", "amira.bensalah@example.com", "+216 20 111 001", "2004-03-14", "female", "Web Development", 2, 16.4, "active", "Nabeul"),
    ("Yassine", "Trabelsi", "yassine.trabelsi@example.com", "+216 20 111 002", "2003-11-02", "male", "Software Engineering", 3, 14.8, "active", "Tunis"),
    ("Salma", "Gharbi", "salma.gharbi@example.com", "+216 20 111 003", "2002-07-21", "female", "Data Science", 3, 17.2, "active", "Sfax"),
    ("Karim", "Jebali", "karim.jebali@example.com", "+216 20 111 004", "2001-01-30", "male", "Networks & Telecom", 3, 12.9, "graduated", "Sousse"),
    ("Mariem", "Haddad", "mariem.haddad@example.com", "+216 20 111 005", "2004-09-09", "female", "Web Development", 1, 15.1, "active", "Hammamet"),
    ("Omar", "Mejri", "omar.mejri@example.com", "+216 20 111 006", "2003-05-17", "male", "Management Information Systems", 2, 11.3, "suspended", "Bizerte"),
    ("Ines", "Khelifi", "ines.khelifi@example.com", "+216 20 111 007", "2002-12-05", "female", "Software Engineering", 3, 18.0, "graduated", "Monastir"),
    ("Mohamed", "Sassi", "mohamed.sassi@example.com", "+216 20 111 008", "2004-02-26", "male", "Data Science", 1, None, "active", "Kairouan"),
    ("Rania", "Chaouch", "rania.chaouch@example.com", "+216 20 111 009", "2003-08-11", "female", "Networks & Telecom", 2, 13.6, "active", "Gabes"),
    ("Hamza", "Zouari", "hamza.zouari@example.com", "+216 20 111 010", "2001-06-19", "male", "Web Development", 3, 15.9, "graduated", "Nabeul"),
    ("Nour", "Ayari", "nour.ayari@example.com", "+216 20 111 011", "2004-04-03", "female", "Management Information Systems", 1, 14.2, "active", "Tunis"),
    ("Firas", "Bouzid", "firas.bouzid@example.com", "+216 20 111 012", "2003-10-28", "male", "Software Engineering", 2, 10.7, "active", "Ariana"),
    ("Sirine", "Mansouri", "sirine.mansouri@example.com", "+216 20 111 013", "2002-03-08", "female", "Data Science", 3, 16.8, "active", "Sfax"),
    ("Aymen", "Dridi", "aymen.dridi@example.com", "+216 20 111 014", "2004-01-15", "male", "Networks & Telecom", 1, 12.4, "active", "Sousse"),
]


def build_record(row):
    first, last, email, phone, dob, gender, course, year, average, status, city = row
    return {
        "first_name": first,
        "last_name": last,
        "email": email,
        "phone": phone,
        "date_of_birth": dob,
        "gender": gender,
        "course": course,
        "year": year,
        "average": average,
        "status": status,
        "address": f"{city}, Tunisia",
    }


def create_demo_users():
    for username, role in (("admin", "admin"), ("staff", "staff")):
        if accounts.get_by_username(username):
            print(f"Account '{username}' already exists: left unchanged.")
            continue
        password = "Demo" + secrets.token_urlsafe(8) + "7"
        accounts.create_user(username, password, role)
        print(f"Created {role} account: username={username}  password={password}")


def main(argv):
    reset = "--reset" in argv
    app = create_app()
    with app.app_context():
        if "--demo-users" in argv:
            create_demo_users()
        db = get_db()
        if reset:
            db.execute("DELETE FROM students")
            db.commit()
        elif db.execute("SELECT COUNT(*) FROM students").fetchone()[0]:
            print("Table is not empty: nothing added. Use --reset to start over.")
            return 0

        for row in DEMO_STUDENTS:
            clean, errors = validate_student(build_record(row), creating=True)
            if errors:
                raise SystemExit(f"Invalid demo record {row[2]}: {errors}")
            repo.create_student(clean)
        print(f"Added {len(DEMO_STUDENTS)} demo students.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
