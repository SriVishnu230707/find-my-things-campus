"""Photo normalization, upload bounds, private inboxes and transaction regressions."""

import json
import sqlite3
import unittest
from contextlib import closing
from io import BytesIO
from pathlib import Path

import test_api
from PIL import Image, PngImagePlugin


class Phase8API(test_api.ReportAPI):
    def picture(self, color="red", size=(80, 40)):
        data = BytesIO()
        info = PngImagePlugin.PngInfo()
        info.add_text("GPS", "secret-location-do-not-retain")
        Image.new("RGB", size, color).save(data, "PNG", pnginfo=info)
        return data.getvalue()

    def upload(
        self, item_id, data, content_type="image/png", token=None, chunked=False
    ):
        boundary = "campus-test-boundary"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="../../untrusted.png"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if token is not None:
            headers["Authorization"] = token
        return self.raw_request(
            "PUT",
            f"/items/{item_id}/photo",
            iter([body[:100], body[100:]]) if chunked else body,
            headers,
            chunked,
        )

    def test_phase8_photo_lifecycle_and_metadata(self):
        item = self.request("POST", "/items", test_api.REPORT)[1]
        self.assertIsNone(item["photo_url"])
        code, body, _ = self.upload(item["id"], self.picture(size=(2000, 1000)))
        self.assertEqual(code, 200)
        photo_url = json.loads(body)["photo_url"]
        code, data, headers = self.raw_request("GET", photo_url)
        self.assertEqual(code, 200)
        self.assertEqual(headers["content-type"], "image/jpeg")
        self.assertNotIn(b"secret-location", data)
        with Image.open(BytesIO(data)) as image:
            self.assertLessEqual(max(image.size), 1600)
            self.assertFalse(image.getexif())
            self.assertEqual(image.format, "JPEG")
        code, body, _ = self.upload(item["id"], self.picture("blue"), chunked=True)
        self.assertEqual(code, 200)
        self.assertNotEqual(json.loads(body)["photo_url"], photo_url)
        self.stop_server()
        self.start_server()
        self.assertEqual(self.raw_request("GET", f"/items/{item['id']}/photo")[0], 200)
        self.assertIsNone(
            self.request("DELETE", f"/items/{item['id']}/photo")[1]["photo_url"]
        )
        self.assertEqual(self.raw_request("GET", photo_url)[0], 404)
        self.upload(item["id"], self.picture())
        self.assertEqual(self.request("DELETE", f"/items/{item['id']}")[0], 204)
        self.assertEqual(self.raw_request("GET", photo_url)[0], 404)

    def test_phase8_photo_permissions_and_invalid_uploads(self):
        item = self.request("POST", "/items", test_api.REPORT)[1]
        _, other = self.account("photo-other")
        self.assertEqual(self.upload(item["id"], self.picture(), token="")[0], 401)
        self.assertEqual(
            self.upload(item["id"], self.picture(), token="Bearer " + other)[0], 403
        )
        self.assertEqual(
            self.request("DELETE", f"/items/{item['id']}/photo", token=other)[0], 403
        )
        for data, media, status in [
            (b"<svg></svg>", "image/svg+xml", 415),
            (b"broken", "image/png", 422),
            (self.picture(), "image/jpeg", 415),
            (b"", "image/png", 422),
            (self.picture(size=(6001, 1)), "image/png", 422),
            (b"x" * (2 * 1024 * 1024 + 1), "image/png", 413),
        ]:
            self.assertEqual(self.upload(item["id"], data, media)[0], status)
        self.assertIsNone(self.request("GET", f"/items/{item['id']}")[1]["photo_url"])
        self.assertEqual(
            self.upload(item["id"], b"x" * (2 * 1024 * 1024 + 20000), chunked=True)[0],
            413,
        )
        self.assertEqual(self.upload(item["id"], self.picture())[0], 200)
        original = self.raw_request("GET", f"/items/{item['id']}/photo")[1]
        self.assertEqual(self.upload(item["id"], b"broken")[0], 422)
        self.assertEqual(
            self.raw_request("GET", f"/items/{item['id']}/photo")[1], original
        )
        self.request("POST", f"/items/{item['id']}/archive")
        self.assertEqual(self.upload(item["id"], self.picture())[0], 409)
        self.assertEqual(self.request("DELETE", f"/items/{item['id']}/photo")[0], 409)

    def test_phase8_private_notifications_and_competing_claims(self):
        _, a = self.account("notify-a")
        _, b = self.account("notify-b")
        item = self.request("POST", "/items", {**test_api.REPORT, "type": "found"})[1]
        evidence = "PRIVATE owner details should never enter a notification"
        claims = [
            self.request(
                "POST", f"/items/{item['id']}/claims", {"evidence": evidence}, token=t
            )[1]
            for t in [a, b]
        ]
        inbox = self.request("GET", "/notifications")[1]
        self.assertEqual(len(inbox), 2)
        self.assertNotIn(evidence, json.dumps(inbox))
        self.assertEqual(self.request("GET", "/notifications", token=None)[0], 401)
        self.assertEqual(self.request("GET", "/notifications", token=a)[1], [])
        self.assertEqual(
            self.request("PATCH", f"/notifications/{inbox[0]['id']}/read", token=a)[0],
            404,
        )
        self.assertEqual(
            self.request("PATCH", f"/notifications/{inbox[0]['id']}/read")[0], 200
        )
        self.assertEqual(
            self.request("GET", "/notifications/unread-count")[1]["unread_count"], 1
        )
        self.assertEqual(
            len(self.request("GET", "/notifications?unread_only=true")[1]), 1
        )
        first = claims[0]["id"]
        second = claims[1]["id"]
        self.request("PATCH", f"/claims/{first}/decision", {"decision": "approved"})
        self.assertEqual(
            self.request(
                "PATCH", f"/claims/{second}/decision", {"decision": "approved"}
            )[0],
            409,
        )
        self.assertEqual(self.request("GET", "/notifications", token=b)[1], [])
        self.request("POST", f"/claims/{first}/handover")
        self.assertEqual(
            {n["kind"] for n in self.request("GET", "/notifications", token=a)[1]},
            {"claim_approved", "handover_completed"},
        )
        self.assertEqual(
            self.request("GET", "/notifications", token=b)[1][0]["kind"],
            "claim_rejected",
        )
        self.assertEqual(
            self.request("POST", "/notifications/read-all", token=a)[1]["updated"], 2
        )
        self.assertEqual(
            self.request("GET", "/notifications/unread-count", token=a)[1][
                "unread_count"
            ],
            0,
        )
        self.assertEqual(
            self.request("GET", "/notifications/unread-count", token=b)[1][
                "unread_count"
            ],
            1,
        )
        self.assertEqual(self.request("POST", f"/claims/{first}/handover")[0], 409)
        self.assertEqual(len(self.request("GET", "/notifications", token=a)[1]), 2)
        self.assertEqual(self.request("GET", "/notifications?limit=101")[0], 422)
        self.assertEqual(
            len(self.request("GET", "/notifications?limit=1&offset=1")[1]), 1
        )

    def test_phase8_notifications_rollback_with_failed_submission(self):
        _, student = self.account("notify-rollback")
        item = self.request("POST", "/items", {**test_api.REPORT, "type": "found"})[1]
        database = Path(self.directory.name) / "test.db"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "CREATE TRIGGER reject_test_notification BEFORE INSERT ON notifications BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
            connection.commit()
        try:
            code = self.request(
                "POST",
                f"/items/{item['id']}/claims",
                {"evidence": "Private identifying details"},
                token=student,
            )[0]
            self.assertEqual(code, 503)
            self.assertEqual(self.request("GET", "/claims/me", token=student)[1], [])
        finally:
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("DROP TRIGGER reject_test_notification")
                connection.commit()
        self.assertEqual(
            self.request(
                "POST",
                f"/items/{item['id']}/claims",
                {"evidence": "Private identifying details"},
                token=student,
            )[0],
            201,
        )
        self.assertEqual(len(self.request("GET", "/notifications")[1]), 1)

    def test_phase8_staff_receives_legacy_report_claims(self):
        import subprocess
        import sys

        _, staff = self.account("legacy-notify-staff")
        _, student = self.account("legacy-notify-student")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "set-role",
                "--email",
                "legacy-notify-staff@example.org",
                "--role",
                "staff",
            ],
            env=self.environment,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        item = self.request("POST", "/items", {**test_api.REPORT, "type": "found"})[1]
        with closing(
            sqlite3.connect(Path(self.directory.name) / "test.db")
        ) as connection:
            connection.execute(
                "UPDATE items SET reporter_id=NULL WHERE id=?", (item["id"],)
            )
            connection.commit()
        self.assertEqual(
            self.upload(item["id"], self.picture(), token="Bearer " + staff)[0], 200
        )
        claim = self.request(
            "POST",
            f"/items/{item['id']}/claims",
            {"evidence": "Private owner identification"},
            token=student,
        )[1]
        self.assertEqual(
            self.request("GET", "/notifications", token=staff)[1][0]["kind"],
            "claim_submitted",
        )
        self.assertEqual(self.request("GET", "/notifications")[1], [])
        self.assertEqual(
            self.request(
                "PATCH",
                f"/claims/{claim['id']}/decision",
                {"decision": "approved"},
                token=staff,
            )[0],
            200,
        )
        self.assertEqual(
            self.request("GET", "/notifications", token=student)[1][0]["kind"],
            "claim_approved",
        )
        self.assertEqual(len(self.request("GET", "/notifications", token=staff)[1]), 1)

    def test_phase8_withdraw_notification_and_read_persistence(self):
        _, student = self.account("notify-withdraw")
        item = self.request("POST", "/items", {**test_api.REPORT, "type": "found"})[1]
        claim = self.request(
            "POST",
            f"/items/{item['id']}/claims",
            {"evidence": "Private identifying details"},
            token=student,
        )[1]
        self.request("POST", "/notifications/read-all")
        self.request("POST", f"/claims/{claim['id']}/withdraw", token=student)
        self.assertEqual(
            self.request("GET", "/notifications?unread_only=true")[1][0]["kind"],
            "claim_withdrawn",
        )
        self.stop_server()
        self.start_server()
        self.assertEqual(
            self.request("GET", "/notifications/unread-count")[1]["unread_count"], 1
        )
        self.assertEqual(len(self.request("GET", "/notifications")[1]), 2)


def load_tests(loader, tests, pattern):
    suite = loader.suiteClass(
        Phase8API(name)
        for name in Phase8API.__dict__
        if name.startswith("test_phase8_")
    )
    suite.addTests(loader.loadTestsFromTestCase(ImageResourceTests))
    return suite


class ImageResourceTests(unittest.TestCase):
    def test_busy_image_decoder_returns_retryable_error(self):
        from fastapi import HTTPException

        from app.services.media import image_slots, normalize_image

        image_slots.acquire()
        image_slots.acquire()
        try:
            with self.assertRaises(HTTPException) as error:
                normalize_image(b"photo", "image/png")
            self.assertEqual(error.exception.status_code, 503)
        finally:
            image_slots.release()
            image_slots.release()
