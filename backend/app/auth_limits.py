"""Bounded process-local throttling for the local prototype's auth endpoints."""

from collections import OrderedDict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request


class AuthLimiter:
    def __init__(self, limit=60, window=60, max_clients=1024):
        self.limit = limit
        self.window = window
        self.max_clients = max_clients
        self.clients = OrderedDict()
        self.lock = Lock()

    def allow(self, client, now=None):
        now = monotonic() if now is None else now
        with self.lock:
            calls = self.clients.pop(client, deque())
            while calls and calls[0] <= now - self.window:
                calls.popleft()
            allowed = len(calls) < self.limit
            if allowed:
                calls.append(now)
            self.clients[client] = calls
            if len(self.clients) > self.max_clients:
                self.clients.popitem(last=False)
            return allowed


limiter = AuthLimiter()


def auth_guard(request: Request):
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client):
        raise HTTPException(
            429, "Too many authentication requests", headers={"Retry-After": "60"}
        )
