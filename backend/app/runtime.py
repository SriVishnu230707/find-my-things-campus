"""Deployment settings fail closed instead of silently using development defaults."""

import os
from functools import lru_cache
from urllib.parse import urlsplit

from app.account_config import (
    campus_domains,
    mail_mode,
    public_base_url,
    verification_required,
)


def production():
    return os.environ.get("APP_ENV", "development") == "production"


@lru_cache
def allowed_hosts():
    default = (
        "localhost,127.0.0.1"
        if not production()
        else urlsplit(public_base_url()).hostname or ""
    )
    return tuple(
        value.strip()
        for value in os.environ.get("ALLOWED_HOSTS", default).split(",")
        if value.strip()
    )


@lru_cache
def trusted_origins():
    default = (
        "http://localhost:8000,http://127.0.0.1:8000"
        if not production()
        else public_base_url()
    )
    return frozenset(
        value.strip().rstrip("/")
        for value in os.environ.get("TRUSTED_ORIGINS", default).split(",")
        if value.strip()
    )


def validate_runtime():
    if os.environ.get("APP_ENV", "development") not in {"development", "production"}:
        raise RuntimeError("APP_ENV must be development or production")
    if not allowed_hosts() or any(
        "*" in host or "/" in host or ":" in host for host in allowed_hosts()
    ):
        raise RuntimeError(
            "ALLOWED_HOSTS must list explicit hostnames without ports or wildcards"
        )
    for origin in trusted_origins():
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("TRUSTED_ORIGINS must contain explicit origins")
        if production() and parsed.scheme != "https":
            raise RuntimeError("Production origins require HTTPS")
    if not production():
        return
    if len(os.environ.get("AUTH_SECRET", "").encode()) < 32:
        raise RuntimeError(
            "Production requires a random AUTH_SECRET from the environment"
        )
    if not os.environ.get("DATABASE_URL", "").startswith(
        ("postgresql://", "postgresql+psycopg://", "postgres://")
    ):
        raise RuntimeError("Production requires PostgreSQL")
    if not os.environ.get("REDIS_URL"):
        raise RuntimeError("Production requires a shared REDIS_URL")
    redis = urlsplit(os.environ["REDIS_URL"])
    if (
        redis.scheme not in {"redis", "rediss"}
        or not redis.hostname
        or not redis.password
        or len(redis.password) < 32
    ):
        raise RuntimeError(
            "Production Redis requires authentication with a strong password"
        )
    if (
        os.environ.get("REDIS_REQUIRE_TLS", "true").lower() != "false"
        and redis.scheme != "rediss"
    ):
        raise RuntimeError("External Redis connections require TLS")
    if (
        urlsplit(public_base_url()).scheme != "https"
        or urlsplit(public_base_url()).hostname not in allowed_hosts()
    ):
        raise RuntimeError(
            "Production requires a matching HTTPS PUBLIC_BASE_URL and ALLOWED_HOSTS"
        )
    if public_base_url() not in trusted_origins():
        raise RuntimeError("PUBLIC_BASE_URL must be a trusted origin")
    if mail_mode() != "smtp" or not campus_domains() or not verification_required():
        raise RuntimeError(
            "Production requires SMTP, campus domains and email verification"
        )
    if len(os.environ.get("METRICS_TOKEN", "").encode()) < 32:
        raise RuntimeError(
            "Production requires a private METRICS_TOKEN of at least 32 bytes"
        )
