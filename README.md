# Student Management System

A full-stack web app to manage student records, with sign-in and roles. Flask + SQLite on the back end, plain HTML/CSS/JavaScript on the front end, red theme with light and dark modes.

## Contents

1. [Features](#features)
2. [Quick start](#quick-start)
3. [Accounts and roles](#accounts-and-roles)
4. [Using the app](#using-the-app)
5. [Configuration](#configuration)
6. [Tests](#tests)
7. [API reference](#api-reference)
8. [Project structure](#project-structure)
9. [Deploying](#deploying)
10. [Backups](#backups)
11. [Troubleshooting](#troubleshooting)
12. [Security notes](#security-notes)
13. [Limitations](#limitations)

## Features

**Students**
- Add, edit, delete (with confirmation) and view the details of a student.
- Validation on both client and server: required fields, email format, phone, date of birth, year 1 to 6, average 0 to 20.
- Unique email (case-insensitive) and unique student ID. IDs are generated as `STU-<year>-NNNN` when left blank.
- Search (name, email, ID, course), course and status filters, 9 sort orders, pagination.
- Advanced filters for averages, study year, academic year/semester, and record dates; named filters are saved in the current browser.
- Dashboard cards (total, active, graduated, suspended, average) and a "Students by course" chart.
- In-app alerts for averages below 10/20 and students without an average.
- Academic year and semester fields, plus a per-student history of changes.
- CSV import with preview and duplicate skipping; printable, filter-aware reports that can be saved as PDF.
- Admin-only JSON data backup and restore. User accounts are kept separate from student backups.
- **Export to CSV** of the current filters. Spreadsheet formula injection is neutralised.

**Accounts**
- Sign-in page, sign-out, 8-hour sessions.
- Two roles: **admin** and **staff** (see below).
- Admins create, disable, enable, delete users, change roles and reset passwords from the app.
- Everyone can change their own password.
- **Activity log** (admins): who signed in, failed sign-ins, who added, changed, deleted or exported what.
- Protection against password guessing (temporary lockout), CSRF protection, hashed passwords.

**Interface**
- Light and dark theme (remembered, follows the system by default).
- Responsive: table on desktop, cards on phones. Keyboard accessible, labelled fields, reduced-motion support.
- Course chart bars are keyboard-accessible shortcuts that filter the student list.

## Quick start

Requires **Python 3.10 or newer**. Only one dependency (Flask).

### 1. Get the code and open a terminal in the project folder

```bash
cd student-management-system
```

### 2. (Recommended) create a virtual environment

Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
Windows (PowerShell):
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```
Windows (cmd):
```bat
py -m venv .venv
.venv\Scripts\activate.bat
```
If PowerShell refuses to run the script, run `Set-ExecutionPolicy -Scope Process Bypass` first.

### 3. Install

```bash
pip install -r requirements.txt
```

### 4. Create your first administrator

Nobody can sign in until an account exists. Run:

```bash
python manage.py create-user admin --role admin
```

You are asked for a password (hidden) twice. Rules: 8 to 128 characters, at least one letter and one number, not equal to the username.

### 5. (Optional) load demo students

```bash
python seed.py
```
Adds 14 fictitious students. To also get ready-made demo accounts `admin` and `staff` with random passwords (printed once, in the terminal):
```bash
python seed.py --demo-users
```
`python seed.py --reset` deletes every student first, then reloads the demo data.

### 6. Start the server

```bash
python run.py
```
Open **http://127.0.0.1:5000** and sign in.

Stop the server with `Ctrl+C`.

## Accounts and roles

| Action | staff | admin |
| --- | :---: | :---: |
| View, search, filter, sort students | yes | yes |
| Add and edit students | yes | yes |
| Export CSV | yes | yes |
| Change own password | yes | yes |
| **Delete students** | no | yes |
| **Manage users** (create, role, disable, reset password, delete) | no | yes |
| **Read the activity log** | no | yes |

The server enforces these rules. Hiding a button in the page is only a convenience.

### Managing accounts from the command line

```bash
python manage.py create-user USERNAME [--role admin|staff] [--password PASSWORD]
python manage.py list-users
python manage.py reset-password USERNAME [--password PASSWORD]
python manage.py set-active USERNAME yes|no
```
Without `--password`, the password is asked for (hidden). Prefer that: a password typed on the command line stays in the shell history.

**Lost the admin password?** Run `python manage.py reset-password admin`. It works even when nobody can sign in, and signs that user out everywhere.

Usernames: 3 to 30 characters, letters, numbers, dot, dash, underscore (not case-sensitive).

### Sign-in protection

- 5 failed sign-ins for the same username from the same address, or 20 from one address, block further attempts for 15 minutes (even with the right password).
- Disabling an account, resetting its password, or changing your own password signs the affected sessions out immediately.
- Failed sign-ins are recorded in the activity log.

## Using the app

- **Add student**: button in the red banner. Required fields are marked with `*`. Leave *Student ID* empty to generate one.
- **Study period**: optionally record the academic year (for example `2026-2027`) and semester for each student. Existing records remain unassigned until edited.
- **View / edit / delete**: icons at the end of each row (staff do not see the delete icon).
- **History**: open a student and choose *History* to see their recorded changes.
- **Search and filters**: use the course/status/sort controls or expand *Advanced filters*. Save named filter presets in the current browser.
- **Students by course**: select a bar to filter the list to that course; select it again to clear the course filter.
- **Export CSV**: button in the banner. It exports the students matching the current search and filters (up to 10,000 rows) as a UTF-8 file that Excel opens correctly.
- **Import CSV**: choose a UTF-8 CSV and preview it before importing. Required headers are `first_name`, `last_name`, `email`, and `course`; other recognized fields are optional. Invalid rows and existing email/ID duplicates are skipped and reported. Limit: 10,000 rows.
- **Grade alerts**: dashboard shortcuts filter students with an average below 10/20 or no average.
- **PDF report**: opens a printable report for the current filters. Choose *Print / Save as PDF* and select *Save as PDF* in the browser's print dialog.
- **User menu** (top right): change password; admins also manage users, inspect the activity log, and open *Backup & restore*. Restoring replaces student data/history but leaves user accounts unchanged.
- **Theme**: sun/moon button in the top bar.

## Configuration

Environment variables (all optional):

| Variable | Default | Meaning |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Address to listen on. Use `0.0.0.0` to allow other machines (read [Deploying](#deploying) first) |
| `PORT` | `5000` | Port |
| `FLASK_DEBUG` | off | `1` turns on the debugger. Never in production |
| `DATABASE_PATH` | `instance/students.db` | SQLite file |
| `SECRET_KEY` | generated | Key that signs session cookies. If unset, a random key is created once in `instance/secret_key` |
| `COOKIE_SECURE` | off | `1` sends the session cookie only over HTTPS. Set it whenever the site runs behind HTTPS |

Linux / macOS: `PORT=8000 python run.py`. Windows PowerShell: `$env:PORT=8000; python run.py`.

## Tests

```bash
python -m unittest discover -s tests -v
```
Tests cover student CRUD, migrations, history, validation, CSV import/export, backups, filters, reports, security headers, sign-in, CSRF, roles, and activity logging. They use temporary databases and never touch yours. Password-hashing tests take about 30 seconds.

## API reference

Base path `/api`. JSON in and out. **Every endpoint except `POST /api/auth/login` needs a signed-in session.** Requests that change data (`POST`, `PUT`, `PATCH`, `DELETE`) must also send the header `X-CSRF-Token` with the token returned by login or `/api/auth/me`.

Errors: `401 {"detail": "Sign in required."}`, `403` (wrong role or CSRF), `429` (too many sign-in attempts, with `Retry-After`), validation `400 {"errors": {"field": "message"}}`, other `{"detail": "message"}`.

### Authentication

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/login` | Body `{"username", "password"}`. Sets the session cookie. Returns the user and `csrf` |
| POST | `/auth/logout` | `204` |
| GET | `/auth/me` | Current user and `csrf` |
| POST | `/auth/password` | Body `{"current_password", "new_password"}`. `204`. Other sessions of the user are signed out |

### Students

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| GET | `/students` | any | List. Query: `page`, `page_size` (max 100, default 10), `search`, `course`, `status`, `ordering` |
| GET | `/students/export.csv` | any | CSV of the same advanced filters as the student list |
| POST | `/students/import/preview` | any | Multipart `file` CSV. Validates rows and reports duplicates without writing |
| POST | `/students/import` | any | Multipart `file` CSV. Imports valid rows; duplicates and invalid rows are skipped and reported |
| POST | `/students` | any | Create. `201` and a `Location` header |
| GET | `/students/<id>` | any | One student |
| GET | `/students/<id>/history` | any | Up to 100 newest student change snapshots |
| PUT | `/students/<id>` | any | Replace. Omitted optional fields reset to defaults; `student_id` is kept |
| PATCH | `/students/<id>` | any | Change only the fields sent |
| DELETE | `/students/<id>` | **admin** | `204` |
| GET | `/stats` | any | Totals, overall average, `by_course` |
| GET | `/alerts` | any | Counts of averages below 10/20 and missing averages |
| GET | `/courses` | any | Distinct course names |

`ordering`: `name`, `-name`, `student_id`, `-student_id`, `course`, `-course`, `year`, `-year`, `average`, `-average`, `created`, `-created` (default).
`status`: `active`, `graduated`, `suspended`.
Advanced filters: `average_min`, `average_max`, `year_min`, `year_max`, `academic_year`, `semester`, `missing_average`, `created_from`, `created_to`.
The authenticated printable report is at `/reports/print` and accepts the same filters.

### Administration (admin only)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/users` | List users |
| POST | `/users` | Create: `{"username", "password", "role"}` |
| PATCH | `/users/<id>` | Any of `role`, `active` (true/false), `password` (reset). You cannot change your own role or disable yourself |
| DELETE | `/users/<id>` | `204`. You cannot delete yourself |
| GET | `/audit` | Activity log, newest first. Query: `page`, `page_size` (max 100, default 20) |
| GET | `/backup` | Download student data/history JSON backup; user accounts are excluded |
| POST | `/backup/restore` | Multipart `file` backup JSON. Replaces student data/history only |

### Example with curl

```bash
# 1. sign in, keep the cookie in a file, read the csrf token from the answer
curl -c cookies.txt -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR-PASSWORD"}'
# -> {"csrf":"abc123...","username":"admin",...}

# 2. read (cookie only)
curl -b cookies.txt "http://127.0.0.1:5000/api/students?search=amira&status=active&ordering=-average"

# 3. write (cookie + CSRF header)
curl -b cookies.txt -X POST http://127.0.0.1:5000/api/students \
  -H "Content-Type: application/json" -H "X-CSRF-Token: abc123..." \
  -d '{"first_name":"Amira","last_name":"Ben Salah","email":"amira@example.com","course":"Web Development","year":2,"average":15.5}'

# 4. export
curl -b cookies.txt -o students.csv "http://127.0.0.1:5000/api/students/export.csv?status=active"
```

## Project structure

```
run.py                dev server (warns when no account exists)
manage.py             account management CLI
seed.py               demo students (and optional demo accounts)
requirements.txt
sms/__init__.py       app factory, session settings, security headers, error handlers
sms/auth.py           sign-in, sessions, roles, CSRF, lockout
sms/accounts.py       users, password rules, activity log (SQL)
sms/admin.py          /api/users and /api/audit
sms/api.py            students API, stats, CSV export
sms/validation.py     student input validation
sms/repository.py     student SQL (parameterised; ORDER BY uses a whitelist)
sms/db.py             SQLite connection and schema
sms/templates/        index.html (app), login.html
sms/static/           css/app.css, js/app.js, js/login.js, js/theme.js
tests/                test_api.py, test_auth.py
instance/             created at run time: students.db, secret_key (not for version control)
```

## Deploying

The built-in server (`python run.py`) is for development. For real use:

1. **Use a production server.** Example with waitress (works on Windows too):
   ```bash
   pip install waitress
   waitress-serve --listen=127.0.0.1:8000 run:app
   ```
   On Linux you can use gunicorn: `pip install gunicorn && gunicorn -w 1 -b 127.0.0.1:8000 run:app`.
   Keep **one worker process**: the sign-in lockout counters live in memory, and SQLite handles one writer at a time.
2. **Put it behind HTTPS** (nginx, Caddy, Apache or your host's proxy) and set `COOKIE_SECURE=1`. Without HTTPS, passwords and session cookies travel in clear text.
3. **Set a fixed `SECRET_KEY`** from a password manager or `python -c "import secrets; print(secrets.token_hex(32))"`.
4. **Reverse proxy and client address**: the lockout uses the client address Flask sees. Behind a proxy that is the proxy's address unless you configure forwarded headers (for example with `werkzeug.middleware.proxy_fix.ProxyFix`), so one attacker could lock everybody out of an account. Configure it before relying on the lockout.
5. Create the first admin with `manage.py` on the server, then change that password in the app.

## Backups

Admins can download a JSON backup from **User menu → Backup & restore** while the app is running. It includes student data and history, but excludes user accounts. Restoring replaces all student data/history after confirmation; create a backup first. Keep backup files private because they contain personal information.

For a complete database copy, everything lives in one file: `instance/students.db` (or `DATABASE_PATH`). Stop the server and copy the file, or, while running:
```bash
sqlite3 instance/students.db ".backup backup.db"
```
Keep `instance/secret_key` private; losing it only signs everyone out.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `No accounts exist yet` when starting | Run `python manage.py create-user admin --role admin` |
| Cannot sign in | Check the username and password. After 5 failures wait 15 minutes, or restart the server (counters are in memory). Reset with `python manage.py reset-password USERNAME` |
| `python` not found on Windows | Use `py` instead of `python`; reinstall Python with "Add to PATH" |
| `ModuleNotFoundError: flask` | Activate the virtual environment, then `pip install -r requirements.txt` |
| `Address already in use` | Another program uses the port: `PORT=5001 python run.py` |
| Signed out all the time after restarts | Set a fixed `SECRET_KEY`, or make sure `instance/` is writable and not wiped |
| "Missing or invalid CSRF token" from scripts | Send `X-CSRF-Token` on every write, using the token from the login answer, and keep the same cookie |
| `database is locked` | Another process is writing. Use a single server process |
| Excel shows odd characters in the CSV | Open it with *Data > From text/CSV* and choose UTF-8, or just double-click (the file has a UTF-8 marker) |
| Start over | Stop the server and delete the `instance/` folder (this deletes all students and accounts) |

## Security notes

- Passwords are stored as salted hashes (Werkzeug scrypt). They are never logged or returned by the API.
- Sessions use a signed, `HttpOnly`, `SameSite=Lax` cookie; the session id is renewed at every sign-in. Writes need a CSRF token.
- All SQL is parameterised; sort orders come from a whitelist; `LIKE` wildcards in searches are escaped.
- The interface writes data with `textContent` / DOM nodes, never `innerHTML`. A strict Content-Security-Policy is sent (no inline scripts or styles, no external resources). API responses and the main page are sent with `Cache-Control: no-store`.
- Sign-in errors do not reveal whether a username exists.
- Student records contain personal data (name, email, phone, date of birth, address). If you use real data, check your local data-protection rules, use HTTPS and back up securely.

## Limitations

- **SQLite only.** Not tested with MySQL or PostgreSQL. Moving means replacing `sms/db.py` and the SQL in `sms/repository.py` and `sms/accounts.py` (or introducing SQLAlchemy and a driver).
- Lockout counters are per process and lost on restart. There is no password-reset by email, no two-factor authentication, no self-service sign-up (admins create accounts).
- Saved filter presets are local to the browser and are not shared across devices.
- PDF creation uses the browser's print-to-PDF feature.
- Demo data is fictitious. The average is on a 0 to 20 scale.
- Browser testing was done in Chromium (Playwright) only. Firefox and Safari were not tested.
