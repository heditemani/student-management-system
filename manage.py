"""Account management from the command line.

    python manage.py create-user USERNAME [--role admin|staff] [--password PASSWORD]
    python manage.py list-users
    python manage.py reset-password USERNAME [--password PASSWORD]
    python manage.py set-active USERNAME yes|no

Without --password the password is asked for (hidden), which keeps it out of the shell history.
"""

import argparse
import getpass
import sys

from sms import accounts, create_app


def ask_password(username):
    while True:
        first = getpass.getpass("Password: ")
        problem = accounts.password_problem(first, username)
        if problem:
            print(problem)
            continue
        if first != getpass.getpass("Repeat password: "):
            print("Passwords do not match.")
            continue
        return first


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user")
    create.add_argument("username")
    create.add_argument("--role", choices=accounts.ROLES, default="staff")
    create.add_argument("--password")

    sub.add_parser("list-users")

    reset = sub.add_parser("reset-password")
    reset.add_argument("username")
    reset.add_argument("--password")

    active = sub.add_parser("set-active")
    active.add_argument("username")
    active.add_argument("value", choices=("yes", "no"))

    args = parser.parse_args(argv)
    app = create_app()
    with app.app_context():
        if args.command == "list-users":
            users = accounts.list_users()
            if not users:
                print("No users yet. Create one with: python manage.py create-user admin --role admin")
            for u in users:
                state = "active" if u["active"] else "disabled"
                print(f"{u['username']:<20} {u['role']:<6} {state:<8} last login: {u['last_login'] or 'never'}")
            return 0

        if args.command == "create-user":
            if not accounts.USERNAME_RE.match(args.username):
                print("Username: 3 to 30 characters: letters, numbers, dot, dash or underscore.")
                return 1
            clean = {"username": args.username}
            password = args.password or ask_password(args.username)
            problem = accounts.password_problem(password, args.username)
            if problem:
                print(problem)
                return 1
            try:
                accounts.create_user(clean["username"], password, args.role)
            except accounts.DuplicateUser:
                print("That username already exists.")
                return 1
            accounts.audit("user.create", clean["username"], f"role {args.role} (CLI)", username="cli")
            print(f"Created {args.role} account '{clean['username']}'.")
            return 0

        row = accounts.get_by_username(args.username)
        if row is None:
            print("No such user.")
            return 1

        if args.command == "reset-password":
            password = args.password or ask_password(row["username"])
            problem = accounts.password_problem(password, row["username"])
            if problem:
                print(problem)
                return 1
            accounts.set_password(row["id"], password)
            accounts.audit("user.update", row["username"], "password reset (CLI)", username="cli")
            print("Password changed. Existing sessions of this user were signed out.")
            return 0

        if args.command == "set-active":
            accounts.set_active(row["id"], args.value == "yes")
            accounts.audit("user.update", row["username"], "enabled (CLI)" if args.value == "yes" else "disabled (CLI)", username="cli")
            print(f"Account '{row['username']}' is now {'active' if args.value == 'yes' else 'disabled'}.")
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
