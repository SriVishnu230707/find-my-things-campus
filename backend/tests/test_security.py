"""Local rate-limit, signing configuration, and hash-safety checks."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException

from app.auth_limits import AuthLimiter
from app.security import hash_password, hash_slots, signing_secret


class SecurityTests(unittest.TestCase):
    def test_rate_limit_expires_and_bounds_memory(self):
        limiter = AuthLimiter(limit=2, window=60, max_clients=2)
        self.assertTrue(limiter.allow("one", now=0))
        self.assertTrue(limiter.allow("one", now=1))
        self.assertFalse(limiter.allow("one", now=2))
        self.assertTrue(limiter.allow("one", now=60))
        limiter.allow("two", now=60)
        limiter.allow("three", now=60)
        self.assertEqual(len(limiter.clients), 2)

    def test_weak_signing_secret_is_rejected(self):
        signing_secret.cache_clear()
        try:
            with patch.dict(os.environ, {"AUTH_SECRET": "short"}):
                with self.assertRaises(RuntimeError):
                    signing_secret()
        finally:
            signing_secret.cache_clear()

    def test_hash_concurrency_returns_retryable_error(self):
        hash_slots.acquire()
        hash_slots.acquire()
        try:
            with self.assertRaises(HTTPException) as error:
                hash_password("Test-password-123")
            self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(error.exception.headers["Retry-After"], "1")
        finally:
            hash_slots.release()
            hash_slots.release()
