"""Argon2id password hashing and strictly verified short-lived JWTs."""

import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from threading import BoundedSemaphore

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException

ISSUER = "campus-lost-and-found"
AUDIENCE = "campus-api"
TOKEN_SECONDS = 15 * 60
SECRET_FILE = Path(__file__).resolve().parents[1] / "data" / "auth.secret"
hasher = PasswordHasher()
hash_slots = BoundedSemaphore(2)


@lru_cache
def signing_secret() -> str:
    value = os.environ.get("AUTH_SECRET")
    if value is None:
        try:
            value = SECRET_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            raise RuntimeError(
                "Initialize a signing secret with python -m app.cli init-secret or set AUTH_SECRET"
            ) from None
    if len(value.encode("utf-8")) < 32:
        raise RuntimeError(
            "AUTH_SECRET must contain at least 32 bytes; use a randomly generated secret"
        )
    return value


def hash_password(password: str) -> str:
    if not hash_slots.acquire(blocking=False):
        raise HTTPException(
            503, "Authentication temporarily busy", headers={"Retry-After": "1"}
        )
    try:
        return hasher.hash(password)
    finally:
        hash_slots.release()


@lru_cache
def dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def verify_password(encoded: str, password: str) -> bool:
    if not hash_slots.acquire(blocking=False):
        raise HTTPException(
            503, "Authentication temporarily busy", headers={"Retry-After": "1"}
        )
    try:
        try:
            return hasher.verify(encoded, password)
        except (VerificationError, InvalidHashError):
            return False
    finally:
        hash_slots.release()


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(seconds=TOKEN_SECONDS),
            "iss": ISSUER,
            "aud": AUDIENCE,
        },
        signing_secret(),
        algorithm="HS256",
    )


def decode_token(token: str) -> int:
    if len(token) > 2048:
        raise jwt.InvalidTokenError("Token too long")
    payload = jwt.decode(
        token,
        signing_secret(),
        algorithms=["HS256"],
        issuer=ISSUER,
        audience=AUDIENCE,
        options={"require": ["sub", "iat", "exp", "iss", "aud"]},
    )
    subject = payload["sub"]
    if (
        not isinstance(subject, str)
        or not subject.isascii()
        or not subject.isdecimal()
        or len(subject) > 19
    ):
        raise jwt.InvalidTokenError("Invalid subject")
    user_id = int(subject)
    if not 0 < user_id <= 2**63 - 1:
        raise jwt.InvalidTokenError("Invalid subject")
    return user_id
