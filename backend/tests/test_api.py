"""HTTP integration checks using only Python's standard library."""

import http.client
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BACKEND = Path(__file__).resolve().parents[1]
REPORT = dict(
    title="Laptop Charger",
    description="Black Dell 65W charger",
    category="electronics",
    location="Central Library",
    type="lost",
)


class ReportAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary_root = BACKEND.parent / ".verification"
        temporary_root.mkdir(exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=temporary_root)
        cls.addClassCleanup(cls.directory.cleanup)
        cls.environment = {
            **os.environ,
            "DATABASE_URL": "sqlite:///"
            + (Path(cls.directory.name) / "test.db").as_posix(),
            "AUTH_SECRET": secrets.token_urlsafe(48),
            "PYTHONPATH": os.pathsep.join(sys.path),
        }
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(BACKEND / "alembic.ini"),
                "upgrade",
                "head",
            ],
            env=cls.environment,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.port = port
        cls.addClassCleanup(cls.stop_server)
        cls.start_server()
        cls.token = None
        response = cls.request(
            "POST",
            "/auth/register",
            {
                "email": "tester@example.org",
                "display_name": "Test Student",
                "password": "Safe-test-password-123",
            },
        )
        if response[0] != 201:
            raise RuntimeError(f"Registration failed: {response[0]}")
        cls.user_id = response[1]["id"]
        cls.token = cls.request(
            "POST",
            "/auth/login",
            {"username": "tester@example.org", "password": "Safe-test-password-123"},
            form=True,
        )[1]["access_token"]

    @classmethod
    def start_server(cls):
        cls.server = subprocess.Popen(
            # Run the interpreter directly, avoiding the Windows venv launcher
            # child process so terminate/wait truly stops the database server.
            [
                getattr(sys, "_base_executable", sys.executable),
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                str(BACKEND),
                "--port",
                str(cls.port),
            ],
            env=cls.environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            if cls.server.poll() is not None:
                raise RuntimeError("Test server exited during startup")
            try:
                if cls.request("GET", "/health")[0] == 200:
                    return
            except (URLError, TimeoutError):
                time.sleep(0.1)
        raise RuntimeError("Test server failed to start")

    @classmethod
    def stop_server(cls):
        if cls.server.poll() is not None:
            return
        cls.server.terminate()
        try:
            cls.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait()

    @classmethod
    def request(cls, method, path, body=None, token="default", form=False):
        data = (
            (urlencode(body) if form else json.dumps(body)).encode()
            if body is not None
            else None
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
            if form
            else "application/json"
        }
        token = getattr(cls, "token", None) if token == "default" else token
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        request = Request(cls.base + path, data=data, method=method, headers=headers)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.code, json.loads(raw) if raw else None, response.headers

    def tearDown(self):
        # This database was created solely for this test class; never the user's DB.
        import sqlite3

        with closing(
            sqlite3.connect(Path(self.directory.name) / "test.db")
        ) as connection:
            with connection:
                connection.execute("DELETE FROM items")

    def test_full_lifecycle(self):
        code, item, headers = self.request("POST", "/items", REPORT)
        self.assertEqual(code, 201)
        path = f"/items/{item['id']}"
        self.assertEqual(headers["Location"], path)
        self.assertEqual(item["status"], "open")
        self.assertTrue(item["created_at"].endswith("Z"))
        self.assertEqual(self.request("GET", path)[1], item)
        self.assertEqual(self.request("GET", "/items")[1], [item])
        code, updated, _ = self.request("PATCH", path, {"status": "resolved"})
        self.assertEqual(code, 200)
        self.assertEqual(updated["status"], "resolved")
        self.assertEqual(updated["title"], item["title"])
        self.assertEqual(updated["created_at"], item["created_at"])
        self.assertGreaterEqual(updated["updated_at"], item["updated_at"])
        self.assertEqual(self.request("DELETE", path)[:2], (204, None))
        self.assertEqual(self.request("GET", path)[0], 404)
        second = self.request("POST", "/items", REPORT)[1]
        self.assertGreater(second["id"], item["id"])

    def test_create_validation(self):
        invalid = [
            {},
            {**REPORT, "type": "missing"},
            {**REPORT, "title": "   "},
            {**REPORT, "category": "invalid"},
            {**REPORT, "id": 99},
            {**REPORT, "status": "resolved"},
            {**REPORT, "title": "x" * 121},
        ]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/items", body)[0], 422)
        self.assertEqual(self.request("GET", "/items")[1], [])

    def test_invalid_unicode_and_nul_are_rejected(self):
        for title in ["Charger\ud800", "Black\x00wallet"]:
            with self.subTest(title=repr(title)):
                self.assertEqual(
                    self.request("POST", "/items", {**REPORT, "title": title})[0], 422
                )

    def test_deep_json_is_rejected_without_crashing(self):
        code, _, _ = self.raw_request(
            "POST",
            "/items",
            "[" * 1200 + "0" + "]" * 1200,
            {"Content-Type": "application/json"},
        )
        self.assertEqual(code, 422)
        self.assertEqual(self.request("GET", "/health")[0], 200)

    def test_patch_validation_and_preservation(self):
        item = self.request("POST", "/items", REPORT)[1]
        path = f"/items/{item['id']}"
        for changes in [
            {},
            {"title": None},
            {"id": 4},
            {"status": "claimed"},
            {"description": "short"},
            {"location": "   "},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual(self.request("PATCH", path, changes)[0], 422)
                self.assertEqual(self.request("GET", path)[1], item)
        result = self.request("PATCH", path, {"title": "  Dell Charger  "})[1]
        self.assertEqual(result["title"], "Dell Charger")

    def test_missing_and_invalid_ids(self):
        for method, body in [
            ("GET", None),
            ("PATCH", {"status": "resolved"}),
            ("DELETE", None),
        ]:
            self.assertEqual(self.request(method, "/items/999999", body)[0], 404)
            for value in ["abc", "0", "-1", str(2**63)]:
                self.assertEqual(self.request(method, f"/items/{value}", body)[0], 422)

    def test_health_and_documentation(self):
        self.assertEqual(self.request("GET", "/health")[:2], (200, {"status": "ok"}))
        schema = self.request("GET", "/openapi.json")[1]
        self.assertEqual(set(schema["paths"]["/items"]), {"post", "get"})
        self.assertEqual(
            set(schema["paths"]["/items/{item_id}"]), {"get", "patch", "delete"}
        )

    def raw_request(self, method, path, body=None, headers=None, chunked=False):
        connection = http.client.HTTPConnection(
            self.base.removeprefix("http://"), timeout=3
        )
        try:
            extra = {"Authorization": "Bearer " + self.token, **(headers or {})}
            connection.request(
                method, path, body=body, headers=extra, encode_chunked=chunked
            )
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_body_limits_including_chunked(self):
        for chunked in [False, True]:
            body = b"x" * 17000
            if chunked:
                body = iter([body[:9000], body[9000:]])
            code, _, _ = self.raw_request(
                "POST", "/items", body, {"Content-Type": "application/json"}, chunked
            )
            self.assertEqual(code, 413)
        self.assertEqual(self.request("GET", "/items")[1], [])

    def test_browser_origin_and_host_guards(self):
        for origin in ["https://evil.example", "null"]:
            code, _, _ = self.raw_request(
                "POST",
                "/items",
                json.dumps(REPORT),
                {"Origin": origin, "Content-Type": "application/json"},
            )
            self.assertEqual(code, 403)
        self.assertEqual(
            self.raw_request("GET", "/health", headers={"Host": "evil.example"})[0], 400
        )
        self.assertEqual(self.request("GET", "/items")[1], [])
        code, _, _ = self.raw_request(
            "POST",
            "/items",
            json.dumps(REPORT),
            {"Origin": "http://127.0.0.1:8000", "Content-Type": "application/json"},
        )
        self.assertEqual(code, 201)

    def test_bounded_listing(self):
        ids = [self.request("POST", "/items", REPORT)[1]["id"] for _ in range(3)]
        page = self.request("GET", "/items?limit=1&offset=1")[1]
        self.assertEqual([item["id"] for item in page], [ids[1]])
        self.assertEqual(self.request("GET", "/items?offset=99999")[1], [])
        for query in ["limit=101", "limit=0", "offset=-1", f"offset={2**63}"]:
            self.assertEqual(self.request("GET", "/items?" + query)[0], 422)

    def test_safe_validation_errors_and_headers(self):
        code, body, headers = self.request(
            "POST", "/items", {"private": "sensitive-test-value"}
        )
        self.assertEqual(code, 422)
        self.assertNotIn("sensitive-test-value", json.dumps(body))
        self.assertTrue(
            all("input" not in issue and "ctx" not in issue for issue in body["detail"])
        )
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "no-store")
        for method, path, body, extra in [
            ("POST", "/items", "x" * 17000, {}),
            ("POST", "/items", "{}", {"Origin": "https://evil.example"}),
            ("GET", "/health", None, {"Host": "evil.example"}),
        ]:
            _, _, denied_headers = self.raw_request(method, path, body, extra)
            self.assertEqual(denied_headers["x-content-type-options"], "nosniff")
            self.assertEqual(denied_headers["cache-control"], "no-store")

    def search(self, **filters):
        return self.request("GET", "/items?" + urlencode(filters))

    def test_search_title_description_and_combined_filters(self):
        title_match = self.request("POST", "/items", {**REPORT, "type": "found"})[1]
        description_match = self.request(
            "POST",
            "/items",
            {**REPORT, "title": "Black Adapter", "location": "Library second floor"},
        )[1]
        unrelated = self.request(
            "POST",
            "/items",
            {
                **REPORT,
                "title": "Blue Bottle",
                "description": "Blue metal bottle",
                "category": "other",
                "location": "Canteen",
            },
        )[1]
        self.request("PATCH", f"/items/{unrelated['id']}", {"status": "resolved"})
        self.assertEqual(
            {item["id"] for item in self.search(q="  CHARGER  ")[1]},
            {title_match["id"], description_match["id"]},
        )
        self.assertEqual(
            [
                item["id"]
                for item in self.search(
                    q="charger",
                    location="LIBRARY",
                    type="found",
                    category="electronics",
                    status="open",
                )[1]
            ],
            [title_match["id"]],
        )
        for filters, expected in [
            ({"type": "found"}, title_match),
            ({"status": "resolved"}, unrelated),
            ({"category": "other"}, unrelated),
            ({"location": "canteen"}, unrelated),
        ]:
            self.assertEqual(
                [item["id"] for item in self.search(**filters)[1]], [expected["id"]]
            )
        self.assertEqual(self.search(q="not-present-anywhere")[1], [])
        self.assertEqual(self.search(q="charger", status="resolved")[1], [])

    def test_search_literal_wildcards_and_sql_text(self):
        for needle in ["%", "_", "/", "' OR 1=1 --"]:
            item = self.request(
                "POST",
                "/items",
                {**REPORT, "title": "Object " + needle, "location": "Room " + needle},
            )[1]
            self.assertEqual(
                [row["id"] for row in self.search(q=needle)[1]], [item["id"]]
            )
            self.assertEqual(
                [row["id"] for row in self.search(location=needle)[1]], [item["id"]]
            )
            self.request("DELETE", f"/items/{item['id']}")

    def test_query_validation(self):
        for filters in [
            {"q": " "},
            {"q": "x" * 121},
            {"q": "bad\x00text"},
            {"location": " "},
            {"location": "x" * 151},
            {"category": "invalid"},
            {"type": "missing"},
            {"status": "claimed"},
            {"sort": "invalid"},
            {"typo": "value"},
        ]:
            with self.subTest(filters=filters):
                self.assertEqual(self.search(**filters)[0], 422)

    def test_sorted_filtered_pagination(self):
        ids = [
            self.request("POST", "/items", {**REPORT, "title": f"Charger {index}"})[1][
                "id"
            ]
            for index in range(4)
        ]
        self.request(
            "POST",
            "/items",
            {**REPORT, "title": "Water Bottle", "description": "Blue metal bottle"},
        )
        self.assertEqual(
            [row["id"] for row in self.search(q="Charger", sort="oldest")[1]], ids
        )
        self.assertEqual([row["id"] for row in self.search(q="Charger")[1]], ids[::-1])
        self.assertEqual(
            [row["id"] for row in self.search(q="Charger", limit=2, offset=1)[1]],
            ids[::-1][1:3],
        )

    def test_persistence_across_restart(self):
        item = self.request("POST", "/items", REPORT)[1]
        path = f"/items/{item['id']}"
        updated = self.request("PATCH", path, {"status": "resolved"})[1]
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request("GET", path)[1], updated)
        self.request("DELETE", path)
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request("GET", path)[0], 404)

    def test_database_error_is_redacted_and_recovers(self):
        import sqlite3

        database = Path(self.directory.name) / "test.db"
        with closing(sqlite3.connect(database)) as connection:
            with connection:
                connection.execute("ALTER TABLE items RENAME TO unavailable_items")
        try:
            code, body, _ = self.request("POST", "/items", REPORT)
            self.assertEqual(code, 503)
            self.assertEqual(body, {"detail": "Database temporarily unavailable"})
        finally:
            with closing(sqlite3.connect(database)) as connection:
                with connection:
                    connection.execute("ALTER TABLE unavailable_items RENAME TO items")
        self.assertEqual(self.request("POST", "/items", REPORT)[0], 201)

    def account(self, suffix, password="Safe-test-password-456"):
        email = suffix + "@example.org"
        code, user, _ = self.request(
            "POST",
            "/auth/register",
            {"email": email, "display_name": "Other Student", "password": password},
            token=None,
        )
        self.assertEqual(code, 201)
        code, result, _ = self.request(
            "POST",
            "/auth/login",
            {"username": email, "password": password},
            token=None,
            form=True,
        )
        self.assertEqual(code, 200)
        return user, result["access_token"]

    def test_registration_validation_and_password_privacy(self):
        user, token = self.account("registration")
        self.assertEqual(user["role"], "student")
        self.assertNotIn("password", json.dumps(user))
        self.assertEqual(self.request("GET", "/auth/me", token=token)[1], user)
        self.assertEqual(
            self.request(
                "POST",
                "/auth/register",
                {
                    "email": "REGISTRATION@EXAMPLE.ORG",
                    "display_name": "Someone",
                    "password": "Another-password-123",
                },
                token=None,
            )[0],
            409,
        )
        for changes in [
            {"email": "bad-email"},
            {"password": "short"},
            {"password": "x" * 129},
            {"role": "staff"},
            {"display_name": " "},
        ]:
            body = {
                "email": "invalid@example.org",
                "display_name": "Student",
                "password": "Test-password-123",
                **changes,
            }
            code, result, _ = self.request("POST", "/auth/register", body, token=None)
            self.assertEqual(code, 422)
            self.assertNotIn('"input"', json.dumps(result))
            self.assertNotIn('"' + body["password"] + '"', json.dumps(result))
        import sqlite3

        with closing(
            sqlite3.connect(Path(self.directory.name) / "test.db")
        ) as connection:
            encoded = connection.execute(
                "SELECT password_hash FROM users WHERE id=?", (user["id"],)
            ).fetchone()[0]
        self.assertTrue(encoded.startswith("$argon2id$"))
        self.assertNotIn("Safe-test-password", encoded)

    def test_login_failures_and_exact_password(self):
        wrong = self.request(
            "POST",
            "/auth/login",
            {"username": "tester@example.org", "password": "Wrong-password-123"},
            token=None,
            form=True,
        )
        missing = self.request(
            "POST",
            "/auth/login",
            {"username": "missing@example.org", "password": "Wrong-password-123"},
            token=None,
            form=True,
        )
        self.assertEqual(wrong[:2], missing[:2])
        self.assertEqual(wrong[0], 401)
        self.assertEqual(wrong[2]["WWW-Authenticate"], "Bearer")
        self.account("spaces", password="  Password with spaces  ")
        self.assertEqual(
            self.request(
                "POST",
                "/auth/login",
                {"username": "spaces@example.org", "password": "Password with spaces"},
                token=None,
                form=True,
            )[0],
            401,
        )
        self.assertEqual(
            self.request(
                "POST",
                "/auth/login",
                {
                    "username": "TESTER@EXAMPLE.ORG",
                    "password": "Safe-test-password-123",
                },
                token=None,
                form=True,
            )[0],
            200,
        )

    def test_anonymous_and_cross_user_permissions(self):
        item = self.request("POST", "/items", REPORT)[1]
        self.assertEqual(item["reporter_id"], self.user_id)
        self.assertEqual(item["reported_by"], "Test Student")
        _, other_token = self.account("permission")
        path = f"/items/{item['id']}"
        for method, endpoint, body in [
            ("POST", "/items", REPORT),
            ("PATCH", path, {"status": "resolved"}),
            ("DELETE", path, None),
        ]:
            self.assertEqual(self.request(method, endpoint, body, token=None)[0], 401)
        for method, body in [("PATCH", {"status": "resolved"}), ("DELETE", None)]:
            self.assertEqual(
                self.request(method, path, body, token=other_token)[0], 403
            )
        self.assertEqual(self.request("GET", path, token=None)[0], 200)
        self.assertEqual(self.request("GET", "/items?q=charger", token=None)[0], 200)
        self.assertEqual(self.request("GET", path)[1], item)
        for data in [
            {**REPORT, "reported_by": "Someone"},
            {**REPORT, "reporter_id": 9},
        ]:
            self.assertEqual(self.request("POST", "/items", data)[0], 422)
        for changes in [{"reporter_id": 9}, {"reported_by": "Someone"}]:
            self.assertEqual(self.request("PATCH", path, changes)[0], 422)

    def test_expired_tampered_and_invalid_tokens(self):
        import time

        import jwt

        secret = self.environment["AUTH_SECRET"]
        now = int(time.time())
        payload = {
            "sub": str(self.user_id),
            "iat": now,
            "exp": now + 900,
            "iss": "campus-lost-and-found",
            "aud": "campus-api",
        }
        invalid = ["not-a-token", self.token[:-10] + "invalid", "x" * 3000]
        for changes in [
            {"exp": now - 1},
            {"iss": "wrong"},
            {"aud": "wrong"},
            {"sub": str(2**63)},
            {"sub": "-1"},
            {"sub": "99999999"},
        ]:
            invalid.append(
                jwt.encode({**payload, **changes}, secret, algorithm="HS256")
            )
        invalid.append(
            jwt.encode(
                {k: v for k, v in payload.items() if k != "exp"},
                secret,
                algorithm="HS256",
            )
        )
        invalid.append(
            jwt.encode(
                payload, "different-signing-secret-long-enough", algorithm="HS256"
            )
        )
        invalid.append(jwt.encode(payload, "", algorithm="none"))
        for token in invalid:
            with self.subTest(token=token[:12]):
                code, _, headers = self.request("GET", "/auth/me", token=token)
                self.assertEqual(code, 401)
                self.assertEqual(headers["WWW-Authenticate"], "Bearer")

    def test_staff_cli_and_legacy_report_permissions(self):
        staff, token = self.account("moderator")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "set-role",
                "--email",
                staff["email"],
                "--role",
                "staff",
            ],
            env=self.environment,
            cwd=BACKEND,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.assertEqual(
            self.request("GET", "/auth/me", token=token)[1]["role"], "staff"
        )
        own = self.request("POST", "/items", REPORT)[1]
        self.assertEqual(
            self.request(
                "PATCH", f"/items/{own['id']}", {"status": "resolved"}, token=token
            )[0],
            200,
        )
        import sqlite3

        with closing(
            sqlite3.connect(Path(self.directory.name) / "test.db")
        ) as connection:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO items (title,description,category,location,type,reported_by,status,created_at,updated_at) SELECT title,description,category,location,type,'Legacy Student',status,created_at,updated_at FROM items WHERE id=?",
                    (own["id"],),
                )
                legacy_id = cursor.lastrowid
        path = f"/items/{legacy_id}"
        self.assertIsNone(self.request("GET", path)[1]["reporter_id"])
        self.assertEqual(self.request("PATCH", path, {"status": "open"})[0], 403)
        self.assertEqual(self.request("DELETE", path)[0], 403)
        self.assertEqual(
            self.request("PATCH", path, {"status": "open"}, token=token)[0], 200
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "assign-owner",
                "--item-id",
                str(legacy_id),
                "--email",
                "tester@example.org",
            ],
            env=self.environment,
            cwd=BACKEND,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.assertEqual(self.request("PATCH", path, {"status": "resolved"})[0], 200)
        self.assertEqual(self.request("DELETE", path, token=token)[0], 204)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "set-role",
                "--email",
                staff["email"],
                "--role",
                "student",
            ],
            env=self.environment,
            cwd=BACKEND,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.assertEqual(
            self.request("DELETE", f"/items/{own['id']}", token=token)[0], 403
        )

    def test_openapi_protects_writes_and_exposes_oauth2(self):
        schema = self.request("GET", "/openapi.json")[1]
        self.assertEqual(
            schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"][
                "password"
            ]["tokenUrl"],
            "auth/login",
        )
        for path, method in [
            ("/items", "post"),
            ("/items/{item_id}", "patch"),
            ("/items/{item_id}", "delete"),
            ("/auth/me", "get"),
        ]:
            self.assertTrue(schema["paths"][path][method]["security"])
        self.assertNotIn("security", schema["paths"]["/items"]["get"])

    def test_deleted_account_token_and_untrusted_role_claim(self):
        import sqlite3
        import time

        import jwt

        user, token = self.account("removed")
        with closing(
            sqlite3.connect(Path(self.directory.name) / "test.db")
        ) as connection:
            with connection:
                connection.execute("DELETE FROM users WHERE id=?", (user["id"],))
        self.assertEqual(self.request("GET", "/auth/me", token=token)[0], 401)
        other, other_token = self.account("role-claim-owner")
        item = self.request("POST", "/items", REPORT, token=other_token)[1]
        now = int(time.time())
        claimed_staff = jwt.encode(
            {
                "sub": str(self.user_id),
                "iat": now,
                "exp": now + 900,
                "iss": "campus-lost-and-found",
                "aud": "campus-api",
                "role": "staff",
            },
            self.environment["AUTH_SECRET"],
            algorithm="HS256",
        )
        self.assertEqual(
            self.request("DELETE", f"/items/{item['id']}", token=claimed_staff)[0], 403
        )


if __name__ == "__main__":
    unittest.main()
