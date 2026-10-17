"""Release acceptance checks fail safely and exercise the actual HTTP app."""

import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

import test_api

from app import __version__
from app.acceptance import check_release, fetch, validate_origin


class AcceptanceTests(unittest.TestCase):
    def test_origin_rejects_credentials_paths_remote_http_and_invalid_ports(self):
        for value in [
            "http://public.example.org",
            "https://user:secret@example.org",
            "https://example.org/path",
            "https://example.org/?token=secret",
            "http://127.0.0.1:bad",
            "file:///private.db",
            "https://example.org/#secret",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_origin(value)
        self.assertEqual(
            validate_origin("http://127.0.0.1:8000/"), "http://127.0.0.1:8000"
        )

    def test_unavailable_service_fails_without_leaking_exception_text(self):
        def unavailable(url):
            raise URLError("private-password-in-driver-error")

        result = check_release("http://127.0.0.1:8000", request=unavailable)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["checks"]), 15)
        self.assertNotIn("private-password", json.dumps(result))

    def test_redirects_are_not_followed(self):
        from app.acceptance import NoRedirects

        self.assertIsNone(
            NoRedirects().redirect_request(
                None, None, 302, "", {}, "http://remote.example.org"
            )
        )

    def test_oversized_response_is_rejected(self):
        from unittest.mock import MagicMock

        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"x" * (256 * 1024 + 1)
        with patch("app.acceptance.build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(ValueError):
                fetch("http://127.0.0.1:8000/health")


class AcceptanceAPI(test_api.ReportAPI):
    require_verification = True

    def test_release_acceptance_on_running_server_and_detects_regressions(self):
        result = check_release(self.base)
        self.assertTrue(result["passed"], result["checks"])
        self.assertEqual(result["version"], __version__)
        for broken_path in [
            "/ready",
            "/campus/styles.css",
            "/staff/summary",
            "/metrics",
            "/openapi.json",
        ]:
            with self.subTest(path=broken_path):

                def altered(url):
                    if url.endswith(broken_path):
                        return 200, {}, b"{}"
                    return fetch(url)

                self.assertFalse(check_release(self.base, request=altered)["passed"])


def load_tests(loader, tests, pattern):
    suite = loader.loadTestsFromTestCase(AcceptanceTests)
    suite.addTest(
        AcceptanceAPI(
            "test_release_acceptance_on_running_server_and_detects_regressions"
        )
    )
    return suite
