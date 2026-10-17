"""Explicit email delivery and campus identity configuration."""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from email_validator import validate_email


@lru_cache
def campus_domains():
    domains = []
    for entry in os.environ.get("CAMPUS_EMAIL_DOMAINS", "").split(","):
        if entry.strip():
            domains.append(
                validate_email(
                    "test@" + entry.strip(), check_deliverability=False
                ).domain.casefold()
            )
    return tuple(sorted(set(domains)))


def campus_address(email):
    return email.rsplit("@", 1)[-1].casefold() in campus_domains()


def verification_required():
    return os.environ.get("REQUIRE_VERIFIED_EMAIL", "true").lower() == "true"


def mail_directory():
    return Path(
        os.environ.get(
            "MAIL_DIRECTORY", str(Path(__file__).parent.parent / "data" / "mail")
        )
    ).resolve()


def mail_mode():
    return os.environ.get("MAIL_MODE", "local").lower()


def public_base_url():
    return os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def validate_account_config():
    campus_domains()
    if os.environ.get("REQUIRE_VERIFIED_EMAIL", "true").lower() not in {
        "true",
        "false",
    }:
        raise RuntimeError("REQUIRE_VERIFIED_EMAIL must be true or false")
    url = urlsplit(public_base_url())
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path
    ):
        raise RuntimeError(
            "PUBLIC_BASE_URL must be an origin without credentials, path or query"
        )
    if url.scheme != "https" and url.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("PUBLIC_BASE_URL requires HTTPS outside loopback")
    if mail_mode() not in {"local", "smtp"}:
        raise RuntimeError("MAIL_MODE must be local or smtp")
    if mail_mode() == "local" and url.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Local email delivery is only for loopback development")
    if mail_mode() == "smtp":
        if not os.environ.get("SMTP_HOST") or not os.environ.get("SMTP_FROM"):
            raise RuntimeError("SMTP_HOST and SMTP_FROM are required for SMTP delivery")
        if os.environ.get("SMTP_SECURITY", "starttls") not in {"starttls", "ssl"}:
            raise RuntimeError("SMTP_SECURITY must be starttls or ssl")
        if not 1 <= int(os.environ.get("SMTP_PORT", "587")) <= 65535:
            raise RuntimeError("Invalid SMTP_PORT")
        if bool(os.environ.get("SMTP_USERNAME")) != bool(
            os.environ.get("SMTP_PASSWORD")
        ):
            raise RuntimeError(
                "SMTP_USERNAME and SMTP_PASSWORD must be supplied together"
            )
