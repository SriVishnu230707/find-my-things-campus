"""Bounded process metrics and structured request logs without submitted values."""

import json
import logging
import time
import uuid
from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self):
        self.lock = Lock()
        self.counts = Counter()
        self.duration = Counter()

    def observe(self, method, route, status, elapsed):
        key = (
            method
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            else "OTHER",
            route,
            str(status // 100) + "xx",
        )
        with self.lock:
            self.counts[key] += 1
            self.duration[key] += elapsed

    def render(self):
        with self.lock:
            counts, duration = self.counts.copy(), self.duration.copy()
        lines = [
            "# TYPE campus_http_requests_total counter",
            "# TYPE campus_http_request_duration_seconds_sum counter",
            "# TYPE campus_http_request_duration_seconds_count counter",
        ]
        for (method, route, status), count in sorted(counts.items()):
            labels = f"method={json.dumps(method)},route={json.dumps(route)},status_class={json.dumps(status)}"
            key = (method, route, status)
            lines += [
                f"campus_http_requests_total{{{labels}}} {count}",
                f"campus_http_request_duration_seconds_sum{{{labels}}} {duration[key]:.6f}",
                f"campus_http_request_duration_seconds_count{{{labels}}} {count}",
            ]
        return "\n".join(lines) + "\n"


metrics = Metrics()


class RequestObservability:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id, started, status = uuid.uuid4().hex, time.perf_counter(), 500

        async def observed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode())
                ]
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        finally:
            elapsed = time.perf_counter() - started
            matched = scope.get("route")
            route = getattr(matched, "path", "unmatched")
            if scope.get("path", "").startswith("/campus/"):
                route = "/campus/*"
            metrics.observe(scope["method"], route, status, elapsed)
            logging.getLogger("campus.requests").info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": route,
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 2),
                    }
                )
            )
