"""Read-only HTTP acceptance checks for a running Campus release."""

import argparse
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app import __version__

MAX_RESPONSE = 256 * 1024


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_origin(value):
    value = value.rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (
            parsed.scheme == "http"
            and parsed.hostname not in {"localhost", "127.0.0.1"}
        )
    ):
        raise ValueError(
            "Use an HTTPS origin or a localhost HTTP origin without credentials or paths"
        )
    parsed.port  # Validate malformed ports before making any requests.
    return value


def fetch(url):
    request = Request(url, headers={"User-Agent": "Campus-Acceptance/" + __version__})
    opener = build_opener(NoRedirects())
    try:
        response = opener.open(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise ValueError("Response exceeds acceptance check limit")
        return response.status, response.headers, content


def check_release(base_url, request=fetch):
    base_url = validate_origin(base_url)
    results = []

    def check(name, path, predicate):
        try:
            passed = bool(predicate(*request(base_url + path)))
            reason = "passed" if passed else "Unexpected status, headers or response"
        except Exception as error:
            passed = False
            # Exception text or response bodies may contain credentials/private data.
            reason = type(error).__name__
        results.append({"check": name, "passed": passed, "detail": reason})

    check(
        "Liveness",
        "/health",
        lambda s, h, b: s == 200 and json.loads(b) == {"status": "ok"},
    )
    check(
        "Dependency readiness",
        "/ready",
        lambda s, h, b: s == 200 and json.loads(b) == {"status": "ready"},
    )
    check(
        "Request correlation",
        "/health",
        lambda s, h, b: (
            s == 200 and re.fullmatch(r"[0-9a-f]{32}", h.get("x-request-id", ""))
        ),
    )
    check(
        "Application version",
        "/openapi.json",
        lambda s, h, b: s == 200 and json.loads(b)["info"]["version"] == __version__,
    )
    check(
        "Website security",
        "/campus/",
        lambda s, h, b: (
            s == 200
            and b"<html" in b.lower()
            and h.get("x-content-type-options") == "nosniff"
            and h.get("cache-control") == "no-store"
            and "frame-ancestors 'none'" in h.get("content-security-policy", "")
        ),
    )
    check(
        "Website JavaScript",
        "/campus/app.js",
        lambda s, h, b: (
            s == 200 and "javascript" in h.get("content-type", "") and len(b) > 0
        ),
    )
    check(
        "Website stylesheet",
        "/campus/styles.css",
        lambda s, h, b: (
            s == 200 and "text/css" in h.get("content-type", "") and len(b) > 0
        ),
    )
    check(
        "API documentation",
        "/docs",
        lambda s, h, b: s == 200 and b"swagger" in b.lower(),
    )
    check(
        "Account configuration",
        "/auth/config",
        lambda s, h, b: s == 200 and json.loads(b)["verification_required"] is True,
    )
    for name, path in [
        ("Account privacy", "/auth/me"),
        ("Notification privacy", "/notifications"),
        ("Staff access protection", "/staff/summary"),
    ]:
        check(name, path, lambda s, h, b: s == 401)
    check("Metrics protection", "/metrics", lambda s, h, b: s in {401, 404})
    check("Private mail protection", "/campus/data/mail/", lambda s, h, b: s == 404)
    check(
        "Private database protection",
        "/campus/data/campus.db",
        lambda s, h, b: s == 404,
    )
    return {
        "version": __version__,
        "scope": "read-only HTTP acceptance; account workflows and mail delivery require separate verification",
        "passed": all(result["passed"] for result in results),
        "checks": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        result = check_release(args.base_url)
    except ValueError:
        parser.exit(
            2, "Invalid base URL; use a bare HTTPS origin or localhost HTTP origin.\n"
        )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
