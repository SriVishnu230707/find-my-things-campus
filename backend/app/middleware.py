"""Request limits and browser guards for the local API."""

import re

from starlette.responses import JSONResponse

from app.runtime import trusted_origins

MAX_BODY_BYTES = 16 * 1024
LOCAL_ORIGINS = {"http://127.0.0.1:8000", "http://localhost:8000"}


class RequestGuards:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        original_send = send

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"cache-control", b"no-store"),
                ]
                if scope["path"].startswith("/campus/"):
                    message["headers"].append(
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                        )
                    )
            await original_send(message)

        send = guarded_send
        headers = dict(scope["headers"])
        if scope["method"] in {"POST", "PATCH", "PUT", "DELETE"}:
            origin = headers.get(b"origin")
            if origin is not None and origin.decode("latin-1") not in trusted_origins():
                await JSONResponse({"detail": "Untrusted browser origin"}, 403)(
                    scope, receive, send
                )
                return
        # Count actual streamed bytes, including chunked requests. Do not rely
        # on Content-Length, and stop before FastAPI parses an oversized JSON body.
        chunks = []
        size = 0
        photo_upload = scope["method"] == "PUT" and re.fullmatch(
            r"/items/[1-9][0-9]*/photo", scope["path"]
        )
        body_limit = (
            2 * 1024 * 1024 + MAX_BODY_BYTES if photo_upload else MAX_BODY_BYTES
        )
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > body_limit:
                detail = (
                    "Photo request exceeds upload limit"
                    if photo_upload
                    else "Request body exceeds 16 KiB"
                )
                await JSONResponse({"detail": detail}, 413)(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
