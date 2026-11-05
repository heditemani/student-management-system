"""API tests. Run with:  python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sms import accounts, create_app  # noqa: E402

ADMIN = ("admin", "Admin-pass-1")
STAFF = ("staff", "Staff-pass-1")


def student(**overrides):
    data = {
        "first_name": "Amira",
        "last_name": "Ben Salah",
        "email": "amira@example.com",
        "course": "Web Development",
        "year": 2,
        "average": 15.5,
        "status": "active",
    }
    data.update(overrides)
    return data


def sign_in(client, credentials):
    """Log in and send the CSRF token with every later request of this client."""
    response = client.post("/api/auth/login", json={"username": credentials[0], "password": credentials[1]})
    assert response.status_code == 200, response.get_data(as_text=True)
    client.environ_base["HTTP_X_CSRF_TOKEN"] = response.get_json()["csrf"]
    return response


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.app = create_app({"DATABASE": self.db_path, "TESTING": True, "SECRET_KEY": "test-secret"})
        with self.app.app_context():
            accounts.create_user(ADMIN[0], ADMIN[1], "admin")
            accounts.create_user(STAFF[0], STAFF[1], "staff")
        self.client = self.app.test_client()
        sign_in(self.client, ADMIN)

    def tearDown(self):
        os.unlink(self.db_path)

    def create(self, **overrides):
        response = self.client.post("/api/students", json=student(**overrides))
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()


class CreateTests(ApiTestCase):
    def test_create_returns_201_with_generated_id_and_location(self):
        response = self.client.post("/api/students", json=student())
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["student_id"], f"STU-{date.today().year}-0001")
        self.assertEqual(body["full_name"], "Amira Ben Salah")
        self.assertEqual(body["status"], "active")
        self.assertTrue(response.headers["Location"].endswith(f"/api/students/{body['id']}"))

    def test_generated_ids_increase(self):
        first = self.create(email="a@example.com")
        second = self.create(email="b@example.com")
        self.assertEqual(first["student_id"][-4:], "0001")
        self.assertEqual(second["student_id"][-4:], "0002")

    def test_custom_student_id_is_uppercased(self):
        body = self.create(student_id="abc-123")
        self.assertEqual(body["student_id"], "ABC-123")

    def test_defaults_are_applied(self):
        body = self.create(year=None, status=None, average=None)
        self.assertEqual(body["year"], 1)
        self.assertEqual(body["status"], "active")
        self.assertIsNone(body["average"])

    def test_email_is_normalised(self):
        body = self.create(email="  Amira@Example.COM ")
        self.assertEqual(body["email"], "amira@example.com")

    def test_required_fields(self):
        response = self.client.post("/api/students", json={})
        self.assertEqual(response.status_code, 400)
        errors = response.get_json()["errors"]
        for field in ("first_name", "last_name", "email", "course"):
            self.assertIn(field, errors)

    def test_invalid_values(self):
        cases = {
            "email": "not-an-email",
            "average": 25,
            "year": 9,
            "status": "retired",
            "phone": "abc",
            "date_of_birth": "2999-01-01",
            "gender": "robot",
            "student_id": "x",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                response = self.client.post("/api/students", json=student(**{field: value}))
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.get_json()["errors"])

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.create()
        response = self.client.post("/api/students", json=student(email="AMIRA@example.com"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.get_json()["errors"])

    def test_duplicate_student_id_is_rejected(self):
        self.create(student_id="STU-1", email="a@example.com")
        response = self.client.post("/api/students", json=student(student_id="stu-1", email="b@example.com"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("student_id", response.get_json()["errors"])

    def test_body_must_be_a_json_object(self):
        for payload in ("[]", '"text"', "not json"):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/students", data=payload, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("detail", response.get_json())

    def test_html_in_text_is_stored_verbatim(self):
        body = self.create(first_name="<b>Bold</b>")
        self.assertEqual(body["first_name"], "<b>Bold</b>")  # escaping is the UI's job


class ReadTests(ApiTestCase):
    def test_get_one_and_404(self):
        created = self.create()
        self.assertEqual(self.client.get(f"/api/students/{created['id']}").get_json()["email"], "amira@example.com")
        missing = self.client.get("/api/students/9999")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.get_json()["detail"], "Student not found.")

    def test_unknown_api_route_returns_json_404(self):
        response = self.client.get("/api/nothing")
        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.get_json())

    def test_wrong_method_returns_json_405(self):
        response = self.client.delete("/api/students")
        self.assertEqual(response.status_code, 405)
        self.assertIn("detail", response.get_json())

    def test_list_pagination(self):
        for i in range(12):
            self.create(email=f"s{i}@example.com", first_name=f"Name{i}")
        page1 = self.client.get("/api/students?page_size=5").get_json()
        self.assertEqual((page1["count"], page1["pages"], len(page1["results"])), (12, 3, 5))
        page3 = self.client.get("/api/students?page_size=5&page=3").get_json()
        self.assertEqual(len(page3["results"]), 2)
        beyond = self.client.get("/api/students?page_size=5&page=9").get_json()
        self.assertEqual(beyond["results"], [])

    def test_default_ordering_is_newest_first(self):
        self.create(email="a@example.com", first_name="First")
        self.create(email="b@example.com", first_name="Second")
        names = [s["first_name"] for s in self.client.get("/api/students").get_json()["results"]]
        self.assertEqual(names, ["Second", "First"])

    def test_search_filter_and_ordering(self):
        self.create(email="a@example.com", first_name="Amira", last_name="Zed", course="Web Development", average=10)
        self.create(email="b@example.com", first_name="Bilel", last_name="Alpha", course="Data Science", status="graduated", average=18)
        self.create(email="c@example.com", first_name="Chiraz", last_name="Mid", course="Data Science", average=None)

        def names(query):
            body = self.client.get(f"/api/students?{query}").get_json()
            return [s["first_name"] for s in body["results"]]

        self.assertEqual(names("search=amira"), ["Amira"])
        self.assertEqual(names("search=Bilel%20Alpha"), ["Bilel"])
        self.assertEqual(names("search=b%40example"), ["Bilel"])
        self.assertEqual(sorted(names("course=data science")), ["Bilel", "Chiraz"])
        self.assertEqual(names("status=graduated"), ["Bilel"])
        self.assertEqual(names("ordering=name"), ["Bilel", "Chiraz", "Amira"])
        self.assertEqual(names("ordering=-average"), ["Bilel", "Amira", "Chiraz"])  # empty averages last
        self.assertEqual(names("ordering=average"), ["Amira", "Bilel", "Chiraz"])

    def test_search_treats_wildcards_literally(self):
        self.create(email="a@example.com", first_name="Amira")
        self.assertEqual(self.client.get("/api/students?search=%25").get_json()["count"], 0)
        self.assertEqual(self.client.get("/api/students?search=_mira").get_json()["count"], 0)

    def test_sql_injection_attempt_is_harmless(self):
        self.create()
        response = self.client.get("/api/students?search=' OR 1=1 --")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 0)
        self.assertEqual(self.client.get("/api/stats").get_json()["total"], 1)

    def test_invalid_query_parameters(self):
        for query in ("page=0", "page=abc", "page_size=1000", "ordering=email;drop", "status=nope"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/students?{query}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("errors", response.get_json())


class UpdateTests(ApiTestCase):
    def test_put_replaces_record_and_resets_omitted_optionals(self):
        created = self.create(phone="+216 20 111 222", address="Nabeul")
        payload = {
            "first_name": "Amira", "last_name": "Updated",
            "email": "amira@example.com", "course": "Data Science",
        }
        response = self.client.put(f"/api/students/{created['id']}", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["last_name"], "Updated")
        self.assertEqual(body["course"], "Data Science")
        self.assertEqual(body["phone"], "")
        self.assertEqual(body["student_id"], created["student_id"])  # kept

    def test_put_requires_required_fields(self):
        created = self.create()
        response = self.client.put(f"/api/students/{created['id']}", json={"first_name": "Only"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.get_json()["errors"])

    def test_patch_changes_only_given_fields(self):
        created = self.create(phone="+216 20 111 222")
        response = self.client.patch(f"/api/students/{created['id']}", json={"status": "graduated"})
        body = response.get_json()
        self.assertEqual(body["status"], "graduated")
        self.assertEqual(body["phone"], "+216 20 111 222")
        self.assertEqual(body["first_name"], "Amira")

    def test_patch_validates(self):
        created = self.create()
        response = self.client.patch(f"/api/students/{created['id']}", json={"average": 99})
        self.assertEqual(response.status_code, 400)

    def test_update_can_keep_own_email_but_not_take_another(self):
        first = self.create(email="a@example.com")
        self.create(email="b@example.com")
        same = self.client.patch(f"/api/students/{first['id']}", json={"email": "a@example.com"})
        self.assertEqual(same.status_code, 200)
        clash = self.client.patch(f"/api/students/{first['id']}", json={"email": "B@example.com"})
        self.assertEqual(clash.status_code, 400)
        self.assertIn("email", clash.get_json()["errors"])

    def test_update_missing_student_is_404(self):
        self.assertEqual(self.client.put("/api/students/9999", json=student()).status_code, 404)
        self.assertEqual(self.client.patch("/api/students/9999", json={"year": 1}).status_code, 404)


class DeleteAndStatsTests(ApiTestCase):
    def test_delete(self):
        created = self.create()
        response = self.client.delete(f"/api/students/{created['id']}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.get_data(), b"")
        self.assertEqual(self.client.get(f"/api/students/{created['id']}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/students/{created['id']}").status_code, 404)

    def test_stats_on_empty_database(self):
        body = self.client.get("/api/stats").get_json()
        self.assertEqual(body, {"total": 0, "active": 0, "graduated": 0, "suspended": 0,
                                "average": None, "courses": 0, "by_course": []})

    def test_stats_and_courses(self):
        self.create(email="a@example.com", course="Web Development", average=10)
        self.create(email="b@example.com", course="Data Science", status="graduated", average=15)
        self.create(email="c@example.com", course="Data Science", status="suspended", average=None)
        stats = self.client.get("/api/stats").get_json()
        self.assertEqual(stats, {"total": 3, "active": 1, "graduated": 1, "suspended": 1, "average": 12.5,
                                 "courses": 2,
                                 "by_course": [{"course": "Data Science", "count": 2},
                                               {"course": "Web Development", "count": 1}]})
        self.assertEqual(self.client.get("/api/courses").get_json(), ["Data Science", "Web Development"])


class PageTests(ApiTestCase):
    def test_home_page_and_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_static_assets_are_served(self):
        self.assertEqual(self.client.get("/static/css/app.css").status_code, 200)
        self.assertEqual(self.client.get("/static/js/app.js").status_code, 200)

    def test_api_responses_are_not_cached(self):
        self.assertEqual(self.client.get("/api/stats").headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
