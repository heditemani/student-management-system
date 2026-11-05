"""Login, roles, CSRF, user management, audit log and CSV export tests."""

import csv
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_api import ADMIN, STAFF, ApiTestCase, sign_in, student  # noqa: E402


class AnonymousTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.anon = self.app.test_client()

    def test_api_requires_sign_in(self):
        for method, path in (("get", "/api/students"), ("get", "/api/stats"), ("get", "/api/courses"),
                             ("get", "/api/students/export.csv"), ("get", "/api/users"),
                             ("get", "/api/auth/me"), ("post", "/api/students"), ("delete", "/api/students/1")):
            with self.subTest(path=path, method=method):
                response = getattr(self.anon, method)(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json()["detail"], "Sign in required.")

    def test_home_shows_login_page_when_signed_out(self):
        page = self.anon.get("/").get_data(as_text=True)
        self.assertIn('id="login-form"', page)
        self.assertNotIn("add-btn", page)

    def test_home_shows_app_when_signed_in(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="add-btn"', page)
        self.assertIn('data-role="admin"', page)

    def test_static_files_stay_public(self):
        self.assertEqual(self.anon.get("/static/css/app.css").status_code, 200)


class LoginTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.anon = self.app.test_client()

    def login(self, username, password):
        return self.anon.post("/api/auth/login", json={"username": username, "password": password})

    def test_success_returns_user_and_csrf_and_sets_cookie(self):
        response = self.login("ADMIN", ADMIN[1])  # username is case-insensitive
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual((body["username"], body["role"]), ("admin", "admin"))
        self.assertTrue(body["csrf"])
        self.assertNotIn("password", str(body).lower().replace("csrf", ""))
        cookie = response.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_wrong_password_and_unknown_user_look_the_same(self):
        a = self.login("admin", "wrong-pass-1")
        b = self.login("nobody", "wrong-pass-1")
        self.assertEqual((a.status_code, b.status_code), (401, 401))
        self.assertEqual(a.get_json(), b.get_json())

    def test_bad_bodies(self):
        self.assertEqual(self.anon.post("/api/auth/login", data="x", content_type="application/json").status_code, 400)
        self.assertEqual(self.login("", "").status_code, 401)
        self.assertEqual(self.anon.post("/api/auth/login", json={"username": "admin", "password": 123}).status_code, 401)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.assertEqual(self.login("admin", "wrong-pass-1").status_code, 401)
        locked = self.login("admin", ADMIN[1])  # even the right password is refused now
        self.assertEqual(locked.status_code, 429)
        self.assertIn("Retry-After", locked.headers)

    def test_successful_login_resets_counter(self):
        for _ in range(4):
            self.login("admin", "wrong-pass-1")
        self.assertEqual(self.login("admin", ADMIN[1]).status_code, 200)
        for _ in range(4):
            self.login("admin", "wrong-pass-1")
        self.assertEqual(self.login("admin", ADMIN[1]).status_code, 200)

    def test_disabled_user_cannot_sign_in(self):
        user_id = next(u["id"] for u in self.client.get("/api/users").get_json() if u["username"] == "staff")
        self.client.patch(f"/api/users/{user_id}", json={"active": False})
        self.assertEqual(self.login(*STAFF).status_code, 401)

    def test_logout_ends_session(self):
        sign_in(self.anon, ADMIN)
        self.assertEqual(self.anon.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.anon.post("/api/auth/logout").status_code, 204)
        self.assertEqual(self.anon.get("/api/auth/me").status_code, 401)


class CsrfTests(ApiTestCase):
    def test_changes_need_the_token(self):
        raw = self.app.test_client()
        raw.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]})
        response = raw.post("/api/students", json=student())  # cookie, but no header
        self.assertEqual(response.status_code, 403)
        raw.environ_base["HTTP_X_CSRF_TOKEN"] = "wrong"
        self.assertEqual(raw.post("/api/students", json=student()).status_code, 403)
        self.assertEqual(raw.get("/api/students").status_code, 200)  # reads need no token

    def test_token_from_another_session_is_rejected(self):
        other = self.app.test_client()
        sign_in(other, STAFF)
        stolen = other.environ_base["HTTP_X_CSRF_TOKEN"]
        raw = self.app.test_client()
        raw.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]})
        raw.environ_base["HTTP_X_CSRF_TOKEN"] = stolen
        self.assertEqual(raw.post("/api/students", json=student()).status_code, 403)


class RoleTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.app.test_client()
        sign_in(self.staff, STAFF)

    def test_staff_can_add_edit_view_but_not_delete(self):
        created = self.staff.post("/api/students", json=student())
        self.assertEqual(created.status_code, 201)
        pk = created.get_json()["id"]
        self.assertEqual(self.staff.patch(f"/api/students/{pk}", json={"year": 3}).status_code, 200)
        self.assertEqual(self.staff.get(f"/api/students/{pk}").status_code, 200)
        denied = self.staff.delete(f"/api/students/{pk}")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.client.get(f"/api/students/{pk}").status_code, 200)  # still there

    def test_staff_cannot_use_admin_endpoints(self):
        self.assertEqual(self.staff.get("/api/users").status_code, 403)
        self.assertEqual(self.staff.post("/api/users", json={"username": "x1", "password": "Passw0rd1"}).status_code, 403)
        self.assertEqual(self.staff.get("/api/audit").status_code, 403)

    def test_role_change_takes_effect_immediately(self):
        users = {u["username"]: u["id"] for u in self.client.get("/api/users").get_json()}
        pk = self.client.post("/api/students", json=student()).get_json()["id"]
        self.client.patch(f"/api/users/{users['staff']}", json={"role": "admin"})
        self.assertEqual(self.staff.delete(f"/api/students/{pk}").status_code, 204)


class UserAdminTests(ApiTestCase):
    def test_create_list_and_duplicate(self):
        ok = self.client.post("/api/users", json={"username": "newbie", "password": "Passw0rd1", "role": "staff"})
        self.assertEqual(ok.status_code, 201)
        self.assertNotIn("password", ok.get_data(as_text=True).lower())
        dup = self.client.post("/api/users", json={"username": "NEWBIE", "password": "Passw0rd1"})
        self.assertEqual(dup.status_code, 400)
        self.assertIn("username", dup.get_json()["errors"])
        names = [u["username"] for u in self.client.get("/api/users").get_json()]
        self.assertEqual(names, ["admin", "newbie", "staff"])

    def test_validation(self):
        cases = [
            ({"username": "ab", "password": "Passw0rd1"}, "username"),
            ({"username": "bad name", "password": "Passw0rd1"}, "username"),
            ({"username": "okname", "password": "short1"}, "password"),
            ({"username": "okname", "password": "onlyletters"}, "password"),
            ({"username": "okname", "password": "12345678"}, "password"),
            ({"username": "okname1", "password": "okname1"}, "password"),
            ({"username": "okname", "password": "Passw0rd1", "role": "root"}, "role"),
        ]
        for payload, field in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/users", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.get_json()["errors"])

    def test_cannot_lock_yourself_out(self):
        me = next(u["id"] for u in self.client.get("/api/users").get_json() if u["username"] == "admin")
        self.assertEqual(self.client.patch(f"/api/users/{me}", json={"role": "staff"}).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/users/{me}", json={"active": False}).status_code, 400)
        self.assertEqual(self.client.delete(f"/api/users/{me}").status_code, 400)

    def test_delete_and_404(self):
        pk = self.client.post("/api/users", json={"username": "temp1", "password": "Passw0rd1"}).get_json()["id"]
        self.assertEqual(self.client.delete(f"/api/users/{pk}").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/users/{pk}").status_code, 404)
        self.assertEqual(self.client.patch("/api/users/9999", json={"role": "staff"}).status_code, 404)

    def test_admin_password_reset_signs_user_out(self):
        staff = self.app.test_client()
        sign_in(staff, STAFF)
        pk = next(u["id"] for u in self.client.get("/api/users").get_json() if u["username"] == "staff")
        self.assertEqual(self.client.patch(f"/api/users/{pk}", json={"password": "Brand-new-9"}).status_code, 200)
        self.assertEqual(staff.get("/api/students").status_code, 401)
        fresh = self.app.test_client()
        self.assertEqual(fresh.post("/api/auth/login", json={"username": "staff", "password": "Brand-new-9"}).status_code, 200)

    def test_disabling_signs_user_out(self):
        staff = self.app.test_client()
        sign_in(staff, STAFF)
        pk = next(u["id"] for u in self.client.get("/api/users").get_json() if u["username"] == "staff")
        self.client.patch(f"/api/users/{pk}", json={"active": False})
        self.assertEqual(staff.get("/api/students").status_code, 401)


class PasswordChangeTests(ApiTestCase):
    def test_change_password(self):
        other = self.app.test_client()
        sign_in(other, ADMIN)  # second session of the same user
        bad = self.client.post("/api/auth/password", json={"current_password": "nope-12345", "new_password": "Another-pass-2"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("current_password", bad.get_json()["errors"])
        weak = self.client.post("/api/auth/password", json={"current_password": ADMIN[1], "new_password": "weak"})
        self.assertIn("new_password", weak.get_json()["errors"])
        same = self.client.post("/api/auth/password", json={"current_password": ADMIN[1], "new_password": ADMIN[1]})
        self.assertEqual(same.status_code, 400)
        ok = self.client.post("/api/auth/password", json={"current_password": ADMIN[1], "new_password": "Another-pass-2"})
        self.assertEqual(ok.status_code, 204)
        self.assertEqual(self.client.get("/api/students").status_code, 200)  # this session stays
        self.assertEqual(other.get("/api/students").status_code, 401)        # the other one is dropped
        fresh = self.app.test_client()
        self.assertEqual(fresh.post("/api/auth/login", json={"username": "admin", "password": ADMIN[1]}).status_code, 401)
        self.assertEqual(fresh.post("/api/auth/login", json={"username": "admin", "password": "Another-pass-2"}).status_code, 200)


class AuditTests(ApiTestCase):
    def test_actions_are_recorded_with_the_user(self):
        created = self.create()
        self.client.patch(f"/api/students/{created['id']}", json={"status": "graduated", "year": 3})
        self.client.delete(f"/api/students/{created['id']}")
        log = self.client.get("/api/audit").get_json()["results"]
        actions = [(r["action"], r["username"]) for r in log]
        for expected in (("student.create", "admin"), ("student.update", "admin"), ("student.delete", "admin"), ("login", "admin")):
            self.assertIn(expected, actions)
        update = next(r for r in log if r["action"] == "student.update")
        self.assertEqual(update["detail"], "year, status")

    def test_failed_logins_are_recorded(self):
        self.app.test_client().post("/api/auth/login", json={"username": "ghost", "password": "wrong-pass-1"})
        log = self.client.get("/api/audit").get_json()["results"]
        self.assertTrue(any(r["action"] == "login.failed" and r["target"] == "ghost" for r in log))

    def test_pagination_and_bad_params(self):
        for _ in range(3):
            self.client.get("/api/students/export.csv")
        body = self.client.get("/api/audit?page_size=2").get_json()
        self.assertEqual(len(body["results"]), 2)
        self.assertGreaterEqual(body["pages"], 2)
        self.assertEqual(self.client.get("/api/audit?page=abc").status_code, 400)


class ExportTests(ApiTestCase):
    def rows(self, query=""):
        response = self.client.get(f"/api/students/export.csv{query}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        text = response.get_data(as_text=True)
        self.assertTrue(text.startswith("﻿"))
        return list(csv.reader(io.StringIO(text[1:])))

    def test_header_and_rows_follow_filters(self):
        self.create(email="a@example.com", first_name="Amira", course="Web Development")
        self.create(email="b@example.com", first_name="Bilel", course="Data Science", status="graduated")
        everything = self.rows()
        self.assertEqual(everything[0][:3], ["student_id", "first_name", "last_name"])
        self.assertEqual(len(everything), 3)
        only = self.rows("?status=graduated")
        self.assertEqual([r[1] for r in only[1:]], ["Bilel"])
        self.assertEqual(len(self.rows("?search=amira")), 2)

    def test_formulas_are_neutralised_but_phones_survive(self):
        self.create(first_name="=HYPERLINK(\"http://evil\")", last_name="@SUM(A1)", email="x@example.com",
                    phone="+216 20 111 222", address="-2+3 cmd|' /C calc'!A0")
        row = self.rows()[1]
        self.assertTrue(row[1].startswith("'="))
        self.assertTrue(row[2].startswith("'@"))
        self.assertEqual(row[4], "+216 20 111 222")
        self.assertTrue(row[11].startswith("'-"))

    def test_bad_filter_is_rejected(self):
        self.assertEqual(self.client.get("/api/students/export.csv?status=nope").status_code, 400)
        self.assertEqual(self.client.get("/api/students/export.csv?ordering=x;y").status_code, 400)


if __name__ == "__main__":
    unittest.main()
