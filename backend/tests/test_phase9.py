"""Verified identity, single-use recovery and staff authorization regressions."""

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import MagicMock, patch

import test_api


class Phase9API(test_api.ReportAPI):
    require_verification = True
    test_domains = "example.org"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with closing(
            sqlite3.connect(Path(cls.directory.name) / "test.db")
        ) as connection:
            connection.execute(
                "UPDATE users SET email_verified=1 WHERE id=?", (cls.user_id,)
            )
            connection.commit()

    def setUp(self):
        self.stop_server()
        self.start_server()

    def email_token(self, email, purpose):
        directory = Path(self.environment["MAIL_DIRECTORY"])
        matches = []
        for path in directory.glob("*.eml"):
            message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
            if str(message["To"]) == email:
                match = re.search(
                    r"#" + purpose + r"=([A-Za-z0-9_-]+)", message.get_content()
                )
                if match:
                    matches.append((path.stat().st_mtime_ns, match.group(1)))
        self.assertTrue(matches, "Expected private development email")
        return max(matches)[1]

    def request_code(self, email, purpose):
        path = (
            "/auth/verification/request"
            if purpose == "verify"
            else "/auth/password/request"
        )
        self.assertEqual(
            self.request("POST", path, {"email": email}, token=None)[0], 202
        )
        return self.email_token(email, purpose)

    def verify(self, email):
        code = self.request_code(email, "verify")
        self.assertEqual(
            self.request(
                "POST", "/auth/verification/confirm", {"token": code}, token=None
            )[0],
            200,
        )
        return code

    def staff_account(self, suffix):
        user, token = self.account(suffix)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "set-role",
                "--email",
                suffix + "@example.org",
                "--role",
                "staff",
            ],
            env=self.environment,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return user, token

    def test_phase9_verification_gates_writes_and_is_single_use(self):
        self.assertEqual(
            self.request(
                "POST",
                "/auth/register",
                {
                    "email": "student@sub.example.org",
                    "display_name": "Student",
                    "password": "Strong-password-123",
                },
                token=None,
            )[0],
            422,
        )
        user, token = self.account("verify-student")
        self.assertFalse(user["email_verified"])
        self.assertEqual(
            self.request("POST", "/items", test_api.REPORT, token=token)[0], 403
        )
        code = self.verify("verify-student@example.org")
        me = self.request("GET", "/auth/me", token=token)[1]
        self.assertTrue(me["email_verified"])
        self.assertTrue(me["campus_verified"])
        self.assertEqual(
            self.request("POST", "/items", test_api.REPORT, token=token)[0], 201
        )
        self.assertEqual(
            self.request(
                "POST", "/auth/verification/confirm", {"token": code}, token=None
            )[0],
            400,
        )
        with closing(
            sqlite3.connect(Path(self.directory.name) / "test.db")
        ) as connection:
            digests = connection.execute(
                "SELECT digest FROM account_tokens WHERE user_id=?", (user["id"],)
            ).fetchall()
        self.assertIn((hashlib.sha256(code.encode()).hexdigest(),), digests)
        self.assertNotIn(code, json.dumps(digests))

    def test_phase9_password_reset_revokes_sessions_and_preserves_spaces(self):
        _, token = self.account("password-student")
        self.verify("password-student@example.org")
        code = self.request_code("password-student@example.org", "reset")
        self.assertEqual(
            self.request(
                "POST", "/auth/verification/confirm", {"token": code}, token=None
            )[0],
            400,
        )
        password = "  New-exact-password-123  "
        data = {"token": code, "password": password}
        self.assertEqual(
            self.request("POST", "/auth/password/reset", data, token=None)[0], 200
        )
        self.assertEqual(self.request("GET", "/auth/me", token=token)[0], 401)
        self.assertEqual(
            self.request("POST", "/auth/password/reset", data, token=None)[0], 400
        )
        for value, expected in [
            (password, 200),
            (password.strip(), 401),
            ("Safe-test-password-456", 401),
        ]:
            self.assertEqual(
                self.request(
                    "POST",
                    "/auth/login",
                    {"username": "password-student@example.org", "password": value},
                    token=None,
                    form=True,
                )[0],
                expected,
            )
        response = self.request(
            "POST",
            "/auth/password/reset",
            {"token": code, "password": "short"},
            token=None,
        )
        self.assertEqual(response[0], 422)
        self.assertNotIn(code, json.dumps(response[1]))
        self.assertNotIn('"input"', json.dumps(response[1]))

    def test_phase9_expiry_replacement_and_email_cooldown(self):
        user, _ = self.account("expiry-student")
        first = self.request_code("expiry-student@example.org", "verify")
        again = self.request_code("expiry-student@example.org", "verify")
        self.assertEqual(first, again)
        with closing(
            sqlite3.connect(Path(self.directory.name) / "test.db")
        ) as connection:
            connection.execute(
                "UPDATE account_tokens SET created_at='2020-01-01' WHERE user_id=?",
                (user["id"],),
            )
            connection.commit()
        second = self.request_code("expiry-student@example.org", "verify")
        self.assertNotEqual(first, second)
        self.assertEqual(
            self.request(
                "POST", "/auth/verification/confirm", {"token": first}, token=None
            )[0],
            400,
        )
        with closing(
            sqlite3.connect(Path(self.directory.name) / "test.db")
        ) as connection:
            connection.execute(
                "UPDATE account_tokens SET expires_at='2020-01-01' WHERE digest=?",
                (hashlib.sha256(second.encode()).hexdigest(),),
            )
            connection.commit()
        self.assertEqual(
            self.request(
                "POST", "/auth/verification/confirm", {"token": second}, token=None
            )[0],
            400,
        )

    def test_phase9_concurrent_reset_consumes_once(self):
        _, token = self.account("race-student")
        code = self.request_code("race-student@example.org", "reset")

        def reset(password):
            return self.request(
                "POST",
                "/auth/password/reset",
                {"token": code, "password": password},
                token=None,
            )[0]

        passwords = ["Race-password-one-123", "Race-password-two-123"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(reset, passwords)), [200, 400])
        self.assertEqual(self.request("GET", "/auth/me", token=token)[0], 401)
        codes = [
            self.request(
                "POST",
                "/auth/login",
                {"username": "race-student@example.org", "password": password},
                token=None,
                form=True,
            )[0]
            for password in passwords
        ]
        self.assertEqual(sorted(codes), [200, 401])

    def test_phase9_staff_dashboard_controls_and_audit(self):
        student, student_token = self.account("staff-target")
        self.verify("staff-target@example.org")
        staff, staff_token = self.staff_account("staff-admin")
        for path in [
            "/staff/summary",
            "/staff/users",
            "/staff/reports",
            "/staff/claims",
            "/staff/audit",
        ]:
            self.assertEqual(self.request("GET", path, token=None)[0], 401)
            self.assertEqual(self.request("GET", path, token=student_token)[0], 403)
            self.assertEqual(self.request("GET", path, token=staff_token)[0], 200)
        item = self.request("POST", "/items", {**test_api.REPORT, "type": "found"})[1]
        evidence = "PRIVATE identifying details not for audit history"
        claim = self.request(
            "POST",
            f"/items/{item['id']}/claims",
            {"evidence": evidence},
            token=student_token,
        )[1]
        self.assertEqual(
            self.request("GET", "/staff/claims", token=staff_token)[1][0]["id"],
            claim["id"],
        )
        self.assertEqual(
            self.request(
                "PATCH",
                f"/claims/{claim['id']}/decision",
                {"decision": "approved"},
                token=staff_token,
            )[0],
            200,
        )
        self.assertEqual(
            self.request("POST", f"/claims/{claim['id']}/handover", token=staff_token)[
                0
            ],
            200,
        )
        self.assertEqual(
            self.request("POST", f"/items/{item['id']}/archive", token=staff_token)[0],
            200,
        )
        data = {"is_active": False, "reason": "Account under moderation review"}
        self.assertEqual(
            self.request(
                "PATCH", f"/staff/users/{student['id']}/status", data, token=staff_token
            )[0],
            200,
        )
        self.assertEqual(self.request("GET", "/auth/me", token=student_token)[0], 401)
        self.assertEqual(
            self.request(
                "POST",
                "/auth/login",
                {
                    "username": "staff-target@example.org",
                    "password": "Safe-test-password-456",
                },
                token=None,
                form=True,
            )[0],
            401,
        )
        self.assertEqual(
            self.request(
                "PATCH", f"/staff/users/{staff['id']}/status", data, token=staff_token
            )[0],
            409,
        )
        data["is_active"] = True
        self.assertEqual(
            self.request(
                "PATCH", f"/staff/users/{student['id']}/status", data, token=staff_token
            )[0],
            200,
        )
        self.assertEqual(self.request("GET", "/auth/me", token=student_token)[0], 401)
        self.assertEqual(
            self.request(
                "POST",
                "/auth/login",
                {
                    "username": "staff-target@example.org",
                    "password": "Safe-test-password-456",
                },
                token=None,
                form=True,
            )[0],
            200,
        )
        events = self.request("GET", "/staff/audit", token=staff_token)[1]
        self.assertTrue(
            {
                "claim_approved",
                "handover_completed",
                "report_archived",
                "account_disabled",
                "account_enabled",
            }.issubset({event["action"] for event in events})
        )
        self.assertNotIn(evidence, json.dumps(events))
        self.assertEqual(
            self.request("GET", "/staff/users?limit=101", token=staff_token)[0], 422
        )
        self.assertNotIn(
            "password_hash",
            json.dumps(self.request("GET", "/staff/users", token=staff_token)[1]),
        )

    def test_phase9_delivery_failure_is_generic_and_rolls_back(self):
        user, _ = self.account("delivery-student")
        previous = self.environment["MAIL_DIRECTORY"]
        blocked = Path(self.directory.name) / "blocked-mail-path"
        blocked.write_text("test", encoding="utf-8")
        self.environment["MAIL_DIRECTORY"] = str(blocked)
        self.stop_server()
        self.start_server()
        try:
            known = self.request(
                "POST",
                "/auth/password/request",
                {"email": "delivery-student@example.org"},
                token=None,
            )
            unknown = self.request(
                "POST",
                "/auth/password/request",
                {"email": "unknown@example.org"},
                token=None,
            )
            self.assertEqual(known[:2], unknown[:2])
            self.assertEqual(known[0], 202)
            with closing(
                sqlite3.connect(Path(self.directory.name) / "test.db")
            ) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT count(*) FROM account_tokens WHERE user_id=?",
                        (user["id"],),
                    ).fetchone()[0],
                    0,
                )
        finally:
            self.environment["MAIL_DIRECTORY"] = previous
            self.stop_server()
            self.start_server()
        self.request_code("delivery-student@example.org", "reset")

    def test_phase9_failed_reset_does_not_consume_link_or_change_password(self):
        _, old_token = self.account("rollback-reset")
        code = self.request_code("rollback-reset@example.org", "reset")
        database = Path(self.directory.name) / "test.db"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "CREATE TRIGGER fail_reset_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
            connection.commit()
        try:
            self.assertEqual(
                self.request(
                    "POST",
                    "/auth/password/reset",
                    {"token": code, "password": "Replacement-password-123"},
                    token=None,
                )[0],
                503,
            )
            self.assertEqual(self.request("GET", "/auth/me", token=old_token)[0], 200)
        finally:
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("DROP TRIGGER fail_reset_audit")
                connection.commit()
        self.assertEqual(
            self.request(
                "POST",
                "/auth/password/reset",
                {"token": code, "password": "Replacement-password-123"},
                token=None,
            )[0],
            200,
        )

    def test_phase9_audit_survives_report_deletion(self):
        _, staff = self.staff_account("audit-admin")
        item = self.request("POST", "/items", test_api.REPORT)[1]
        self.assertEqual(
            self.request("DELETE", f"/items/{item['id']}", token=staff)[0], 204
        )
        self.assertTrue(
            any(
                event["action"] == "report_deleted" and event["item_id"] == item["id"]
                for event in self.request("GET", "/staff/audit", token=staff)[1]
            )
        )


def load_tests(loader, tests, pattern):
    suite = loader.suiteClass(
        Phase9API(name)
        for name in Phase9API.__dict__
        if name.startswith("test_phase9_")
    )
    suite.addTests(loader.loadTestsFromTestCase(MailTests))
    return suite


class MailTests(unittest.TestCase):
    def test_smtp_uses_tls_and_does_not_save_local_mail(self):
        import os

        from app.services.mail import deliver_account_email

        smtp = MagicMock()
        with (
            patch.dict(
                os.environ,
                {
                    "MAIL_MODE": "smtp",
                    "SMTP_HOST": "smtp.example.org",
                    "SMTP_FROM": "campus@example.org",
                    "SMTP_USERNAME": "test",
                    "SMTP_PASSWORD": "test",
                },
            ),
            patch("app.services.mail.smtplib.SMTP", return_value=smtp),
        ):
            deliver_account_email("student@example.org", "verify", "test-only-token")
        smtp.__enter__.return_value.starttls.assert_called_once()
        smtp.__enter__.return_value.send_message.assert_called_once()
