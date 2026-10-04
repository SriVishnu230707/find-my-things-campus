"""HTTP integration checks using only Python's standard library."""

import json
import http.client
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND = Path(__file__).resolve().parents[1]
REPORT = dict(title="Laptop Charger", description="Black Dell 65W charger",
              category="electronics", location="Central Library", type="lost",
              reported_by="Vishnu")


class ReportAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir",
             str(BACKEND), "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        cls.addClassCleanup(cls.stop_server)
        for _ in range(100):
            try:
                if cls.request("GET", "/health")[0] == 200:
                    return
            except (URLError, TimeoutError):
                time.sleep(0.1)
        raise RuntimeError("Test server failed to start")

    @classmethod
    def stop_server(cls):
        cls.server.terminate()
        try:
            cls.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait()

    @classmethod
    def request(cls, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = Request(cls.base + path, data=data, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.code, json.loads(raw) if raw else None, response.headers

    def tearDown(self):
        for item in self.request("GET", "/items")[1]:
            self.request("DELETE", f"/items/{item['id']}")

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
        invalid = [{}, {**REPORT, "type": "missing"}, {**REPORT, "title": "   "},
                   {**REPORT, "category": "invalid"}, {**REPORT, "id": 99},
                   {**REPORT, "status": "resolved"}, {**REPORT, "title": "x" * 121}]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/items", body)[0], 422)
        self.assertEqual(self.request("GET", "/items")[1], [])

    def test_patch_validation_and_preservation(self):
        item = self.request("POST", "/items", REPORT)[1]
        path = f"/items/{item['id']}"
        for changes in [{}, {"title": None}, {"id": 4}, {"status": "claimed"},
                        {"description": "short"}, {"location": "   "}]:
            with self.subTest(changes=changes):
                self.assertEqual(self.request("PATCH", path, changes)[0], 422)
                self.assertEqual(self.request("GET", path)[1], item)
        result = self.request("PATCH", path, {"title": "  Dell Charger  "})[1]
        self.assertEqual(result["title"], "Dell Charger")

    def test_missing_and_invalid_ids(self):
        for method, body in [("GET", None), ("PATCH", {"status": "resolved"}),
                             ("DELETE", None)]:
            self.assertEqual(self.request(method, "/items/999999", body)[0], 404)
            for value in ["abc", "0", "-1"]:
                self.assertEqual(self.request(method, f"/items/{value}", body)[0], 422)

    def test_health_and_documentation(self):
        self.assertEqual(self.request("GET", "/health")[:2], (200, {"status": "ok"}))
        schema = self.request("GET", "/openapi.json")[1]
        self.assertEqual(set(schema["paths"]["/items"]), {"post", "get"})
        self.assertEqual(set(schema["paths"]["/items/{item_id}"]), {"get", "patch", "delete"})

    def raw_request(self, method, path, body=None, headers=None, chunked=False):
        connection = http.client.HTTPConnection(self.base.removeprefix("http://"), timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {}, encode_chunked=chunked)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_body_limits_including_chunked(self):
        for chunked in [False, True]:
            body = b"x" * 17000
            if chunked:
                body = iter([body[:9000], body[9000:]])
            code, _, _ = self.raw_request("POST", "/items", body,
                                         {"Content-Type": "application/json"}, chunked)
            self.assertEqual(code, 413)
        self.assertEqual(self.request("GET", "/items")[1], [])

    def test_browser_origin_and_host_guards(self):
        for origin in ["https://evil.example", "null"]:
            code, _, _ = self.raw_request("POST", "/items", json.dumps(REPORT),
                    {"Origin": origin, "Content-Type": "application/json"})
            self.assertEqual(code, 403)
        self.assertEqual(self.raw_request("GET", "/health", headers={"Host": "evil.example"})[0], 400)
        self.assertEqual(self.request("GET", "/items")[1], [])
        code, _, _ = self.raw_request("POST", "/items", json.dumps(REPORT),
                    {"Origin": "http://127.0.0.1:8000", "Content-Type": "application/json"})
        self.assertEqual(code, 201)

    def test_bounded_listing(self):
        ids = [self.request("POST", "/items", REPORT)[1]["id"] for _ in range(3)]
        page = self.request("GET", "/items?limit=1&offset=1")[1]
        self.assertEqual([item["id"] for item in page], [ids[1]])
        self.assertEqual(self.request("GET", "/items?offset=99999")[1], [])
        for query in ["limit=101", "limit=0", "offset=-1"]:
            self.assertEqual(self.request("GET", "/items?" + query)[0], 422)

    def test_safe_validation_errors_and_headers(self):
        code, body, headers = self.request("POST", "/items", {"private": "sensitive-test-value"})
        self.assertEqual(code, 422)
        self.assertNotIn("sensitive-test-value", json.dumps(body))
        self.assertTrue(all("input" not in issue and "ctx" not in issue for issue in body["detail"]))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
