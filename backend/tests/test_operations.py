"""Production settings, rate-limit failure behavior, monitoring and safe backups."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import redis
import test_api
from fastapi import HTTPException

from app.account_config import campus_domains
from app.auth_limits import AuthLimiter, check_limit
from app.observability import Metrics
from app.ops import backup_sqlite
from app.runtime import allowed_hosts, trusted_origins, validate_runtime


class OperationsTests(unittest.TestCase):
    def tearDown(self):
        allowed_hosts.cache_clear()
        trusted_origins.cache_clear()
        campus_domains.cache_clear()

    def test_production_refuses_insecure_defaults(self):
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "AUTH_SECRET": "",
                "PUBLIC_BASE_URL": "https://campus.example.org",
                "ALLOWED_HOSTS": "campus.example.org",
                "TRUSTED_ORIGINS": "https://campus.example.org",
            },
        ):
            allowed_hosts.cache_clear()
            trusted_origins.cache_clear()
            with self.assertRaises(RuntimeError):
                validate_runtime()

    def test_production_accepts_explicit_private_network_configuration(self):
        values = {
            "APP_ENV": "production",
            "AUTH_SECRET": "a" * 64,
            "METRICS_TOKEN": "m" * 64,
            "DATABASE_URL": "postgresql+psycopg://test-only@db/campus",
            "REDIS_URL": "redis://:" + "r" * 64 + "@redis:6379/0",
            "REDIS_REQUIRE_TLS": "false",
            "PUBLIC_BASE_URL": "https://campus.example.org",
            "ALLOWED_HOSTS": "campus.example.org,127.0.0.1",
            "TRUSTED_ORIGINS": "https://campus.example.org",
            "MAIL_MODE": "smtp",
            "CAMPUS_EMAIL_DOMAINS": "example.org",
            "REQUIRE_VERIFIED_EMAIL": "true",
        }
        with patch.dict(os.environ, values):
            allowed_hosts.cache_clear()
            trusted_origins.cache_clear()
            campus_domains.cache_clear()
            validate_runtime()
            with patch.dict(os.environ, {"REDIS_REQUIRE_TLS": "true"}):
                with self.assertRaises(RuntimeError):
                    validate_runtime()

    def test_rate_backend_fails_closed(self):
        from unittest.mock import MagicMock

        client = MagicMock()
        client.eval.side_effect = redis.ConnectionError("test failure")
        with (
            patch("app.auth_limits.redis_client", return_value=client),
            patch("app.security.signing_secret", return_value="s" * 64),
        ):
            with self.assertRaises(HTTPException) as error:
                check_limit("test", "client", 1, AuthLimiter(limit=1))
            self.assertEqual(error.exception.status_code, 503)

    def test_sqlite_backup_integrity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.db"
            destination = Path(directory) / "backup.db"
            with closing(sqlite3.connect(source)) as connection:
                with connection:
                    connection.execute("CREATE TABLE sample (value TEXT)")
                    connection.execute("INSERT INTO sample VALUES ('preserved')")
            with patch(
                "app.ops.database_url", return_value="sqlite:///" + source.as_posix()
            ):
                backup_sqlite(destination)
                with self.assertRaises(FileExistsError):
                    backup_sqlite(destination)
            with closing(sqlite3.connect(destination)) as connection:
                self.assertEqual(
                    connection.execute("SELECT value FROM sample").fetchone()[0],
                    "preserved",
                )

    def test_metrics_export_has_bounded_route_labels(self):
        metric = Metrics()
        metric.observe("GET", "/items/{item_id}", 200, 0.25)
        text = metric.render()
        self.assertIn('route="/items/{item_id}"', text)
        self.assertIn("0.250000", text)


class MonitoringAPI(test_api.ReportAPI):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.environment["METRICS_TOKEN"] = "test-only-monitoring-token-" * 3
        cls.stop_server()
        cls.start_server()

    def test_operations_readiness_metrics_and_request_ids(self):
        self.assertEqual(self.request("GET", "/ready")[:2], (200, {"status": "ready"}))
        code, _, headers = self.request("GET", "/health")
        self.assertEqual(code, 200)
        self.assertEqual(len(headers["X-Request-ID"]), 32)
        self.assertEqual(self.request("GET", "/metrics", token=None)[0], 401)
        code, body, _ = self.raw_request(
            "GET",
            "/metrics",
            headers={"Authorization": "Bearer " + self.environment["METRICS_TOKEN"]},
        )
        self.assertEqual(code, 200)
        self.assertIn(b"campus_http_requests_total", body)
        self.assertNotIn(b"access_token", body)


def load_tests(loader, tests, pattern):
    suite = loader.loadTestsFromTestCase(OperationsTests)
    suite.addTests(
        MonitoringAPI(name)
        for name in MonitoringAPI.__dict__
        if name.startswith("test_operations_")
    )
    return suite
