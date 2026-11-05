"""Start the development server:  python run.py"""

import os

from sms import accounts, create_app

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        if accounts.count_users() == 0:
            print("\nNo accounts exist yet, so nobody can sign in. Create the first one:\n"
                  "    python manage.py create-user admin --role admin\n")
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
