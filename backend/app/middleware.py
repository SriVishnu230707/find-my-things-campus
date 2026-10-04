"""Limits for the local, unauthenticated Phase 2 prototype."""

from starlette.responses import JSONResponse

MAX_BODY_BYTES = 16 * 1024
LOCAL_ORIGINS = {"http://127.0.0.1:8000", "http://localhost:8000"}


class RequestGuards:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        if scope["method"] in {"POST", "PATCH", "PUT", "DELETE"}:
            origin = headers.get(b"origin")
            if origin is not None and origin.decode("latin-1") not in LOCAL_ORIGINS:
                await JSONResponse({"detail": "Untrusted browser origin"}, 403)(scope, receive, send)
                return
        # Count actual streamed bytes, including chunked requests. Do not rely
        # on Content-Length, and stop before FastAPI parses an oversized JSON body.
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                await JSONResponse({"detail": "Request body exceeds 16 KiB"}, 413)(scope, receive, send)
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

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"cache-control", b"no-store"),
                ]
            await send(message)

        await self.app(scope, replay, guarded_send)
