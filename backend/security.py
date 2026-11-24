"""Single-process request budgets applied before FastAPI parses request bodies."""

import asyncio
import os
import threading
import time
from collections import OrderedDict, deque
from starlette.responses import JSONResponse


class AuthAttempts:
    def __init__(self, per_minute=30, global_per_minute=120):
        self.per_minute = per_minute
        self.global_per_minute = global_per_minute
        self.addresses = OrderedDict()
        self.total = deque()
        self.lock = threading.Lock()

    def allow(self, address, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            while self.total and self.total[0] <= now - 60:
                self.total.popleft()
            # Entries expire after one minute. Capacity bounds unsolicited identities.
            while self.addresses:
                key, timestamps = next(iter(self.addresses.items()))
                if timestamps[-1] > now - 60:
                    break
                self.addresses.pop(key)
            attempts = self.addresses.get(address, deque())
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if (
                len(attempts) >= self.per_minute
                or len(self.total) >= self.global_per_minute
            ):
                return False
            if address not in self.addresses and len(self.addresses) >= 4096:
                return False
            attempts.append(now)
            self.addresses[address] = attempts
            self.addresses.move_to_end(address)
            self.total.append(now)
            return True


auth_attempts = AuthAttempts(
    int(os.getenv("AUTH_ATTEMPTS_PER_MINUTE", "30")),
    int(os.getenv("AUTH_GLOBAL_ATTEMPTS_PER_MINUTE", "120")),
)


class RequestLimits:
    def __init__(self, app, body_timeout=30):
        self.app = app
        self.body_timeout = body_timeout
        self.uploads = threading.BoundedSemaphore(2)
        self.auth = threading.BoundedSemaphore(2)
        self.writes = threading.BoundedSemaphore(16)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            await self.app(scope, receive, send)
            return
        path = scope["path"].rstrip("/")
        is_auth = path in {"/api/auth/login", "/api/auth/register"}
        is_upload = path == "/api/workshop/references" or (
            path.startswith("/api/courses/") and path.endswith("/files")
        )
        limit = 64 * 1024
        if is_upload:
            limit = (6 if path == "/api/workshop/references" else 11) * 1024 * 1024
        if is_auth or path == "/api/workshop/payments/mock/notify":
            limit = 4096
        if path == "/api/workshop/payments/alipay/notify":
            limit = 16384

        async def reject(status, message):
            response = JSONResponse(
                {"detail": message},
                status_code=status,
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
            await response(scope, receive, send)

        lengths = [value for key, value in scope["headers"] if key == b"content-length"]
        if lengths:
            try:
                length = int(lengths[0])
                if len(lengths) != 1 or length < 0:
                    raise ValueError
            except ValueError:
                await reject(400, "请求长度无效")
                return
            if length > limit:
                await reject(413, "请求体超过此接口的大小限制")
                return
        address = scope.get("client") or ("unknown", 0)
        if is_auth and not auth_attempts.allow(address[0]):
            await reject(429, "登录或注册尝试过于频繁，请一分钟后重试")
            return
        slots = self.auth if is_auth else self.uploads if is_upload else self.writes
        if not slots.acquire(blocking=False):
            await reject(429, "当前请求较多，请稍后重试")
            return
        try:
            # Buffer only a bounded body, checking chunked transfers as bytes arrive.
            # Upload slots cap this buffer at 22 MiB across the process.
            body = bytearray()
            deadline = time.monotonic() + self.body_timeout
            while True:
                try:
                    message = await asyncio.wait_for(
                        receive(), max(0, deadline - time.monotonic())
                    )
                except TimeoutError:
                    await reject(408, "请求上传超过30秒，请重试或拆分文件")
                    return
                if message["type"] == "http.disconnect":
                    return
                fragment = message.get("body", b"")
                if len(body) + len(fragment) > limit:
                    await reject(413, "请求体超过此接口的大小限制")
                    return
                body.extend(fragment)
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, send)
        finally:
            slots.release()
