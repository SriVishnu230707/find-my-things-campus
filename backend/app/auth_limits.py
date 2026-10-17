"""Bounded process-local throttling for the local prototype's auth endpoints."""

import hashlib
import hmac
import os
import secrets
from collections import OrderedDict, deque
from functools import lru_cache
from threading import Lock
from time import monotonic

import redis
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
write_limiter = AuthLimiter(limit=120)
photo_limiter = AuthLimiter(limit=20)

SLIDING_WINDOW = """
local time = redis.call('TIME')
local now = time[1] * 1000 + math.floor(time[2] / 1000)
local window = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then return 0 end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return 1
"""


@lru_cache
def redis_client():
    url = os.environ.get("REDIS_URL")
    return (
        redis.Redis.from_url(
            url, socket_connect_timeout=2, socket_timeout=2, decode_responses=True
        )
        if url
        else None
    )


def check_limit(group, identity, limit, local_limiter):
    client = redis_client()
    if client is None:
        allowed = local_limiter.allow(identity)
    else:
        from app.security import signing_secret

        digest = hmac.new(
            signing_secret().encode(), str(identity).encode(), hashlib.sha256
        ).hexdigest()
        try:
            allowed = bool(
                client.eval(
                    SLIDING_WINDOW,
                    1,
                    f"campus:rate:{group}:{digest}",
                    limit,
                    60000,
                    secrets.token_hex(16),
                )
            )
        except redis.RedisError:
            raise HTTPException(
                503,
                "Rate-limit service temporarily unavailable",
                headers={"Retry-After": "1"},
            ) from None
    if not allowed:
        raise HTTPException(
            429, "Too many requests; try again shortly", headers={"Retry-After": "60"}
        )


def mutation_guard(request, user_id):
    if request.method in {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    } and not request.url.path.startswith("/auth/"):
        check_limit("writes", user_id, 120, write_limiter)
        if request.method == "PUT" and request.url.path.endswith("/photo"):
            check_limit("photos", user_id, 20, photo_limiter)


def auth_guard(request: Request):
    client = request.client.host if request.client else "unknown"
    check_limit("auth", client, 60, limiter)
