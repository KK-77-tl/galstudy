import asyncio
import json
import subprocess
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import event
from backend.main import app
from backend.db import Session, engine, SourceFile
from backend.security import RequestLimits, AuthAttempts
from backend import main, security


def test_auth_limits_expire_and_bound_global_attempts():
    budget = AuthAttempts(per_minute=2, global_per_minute=3)
    assert budget.allow("first", now=0)
    assert budget.allow("first", now=1)
    assert not budget.allow("first", now=2)
    assert budget.allow("second", now=2)
    assert not budget.allow("third", now=3)
    assert budget.allow("first", now=62)
    assert len(budget.total) == 1
    assert list(budget.addresses) == ["first"]


def test_auth_endpoints_enforce_attempt_budget(monkeypatch):
    monkeypatch.setattr(security, "auth_attempts", AuthAttempts(2, 3))
    with TestClient(app) as client:
        payload = {"email": "missing@example.com", "password": "a-long-password"}
        assert client.post("/api/auth/login", json=payload).status_code == 401
        assert client.post("/api/auth/login", json=payload).status_code == 401
        assert client.post("/api/auth/login", json=payload).status_code == 429


def test_slow_body_timeout_releases_slots():
    async def exercise():
        responses = []

        async def downstream(scope, receive, send):
            raise AssertionError("Timed-out body reached the application")

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            responses.append(message)

        middleware = RequestLimits(downstream, body_timeout=0)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/courses",
            "headers": [],
        }
        await middleware(scope, receive, send)
        assert responses[0]["status"] == 408
        assert middleware.writes.acquire(blocking=False)
        middleware.writes.release()

    asyncio.run(exercise())


def test_deleting_source_during_parse_does_not_publish_or_kill_worker(monkeypatch):
    async def idle():
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "worker", idle)
    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={
                "email": uuid4().hex + "@example.com",
                "password": "delete-during-parse",
            },
        )
        cid = client.post("/api/courses", json={"title": "parse deletion"}).json()["id"]
        fid = client.post(
            f"/api/courses/{cid}/files", files={"file": ("original.pdf", b"pending")}
        ).json()["id"]

        def parsed_after_delete(*args, **kwargs):
            assert client.delete(f"/api/courses/{cid}/files/{fid}").status_code == 200
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {"chunks": [["第1页", "deleted private text"]]}
                ).encode(),
            )

        monkeypatch.setattr(main.subprocess, "run", parsed_after_delete)
        main.process_file(fid)
        detail = client.get(f"/api/courses/{cid}").json()
        assert detail["files"] == []
        assert detail["points"] == []


def test_body_limits_before_validation_with_content_length_and_chunked():
    with TestClient(app) as client:
        for path, limit in [
            ("/api/auth/login", 4096),
            ("/api/courses", 65536),
            ("/api/workshop/payments/mock/notify", 4096),
            ("/api/workshop/references", 6 * 1024 * 1024),
            ("/api/courses/unknown/files", 11 * 1024 * 1024),
        ]:
            response = client.post(
                path, content=b"x", headers={"Content-Length": str(limit + 1)}
            )
            assert response.status_code == 413
            assert response.headers["Cache-Control"] == "no-store"
            # No Content-Length, as with a streaming/chunked upload.
            response = client.post(
                path,
                content=iter([b"x" * (limit // 2), b"y" * (limit - limit // 2 + 1)]),
            )
            assert response.status_code == 413
        assert (
            client.post(
                "/api/auth/login", content=b"", headers={"Content-Length": "-1"}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "x@y.com", "password": "valid-long-password"},
                headers={"Origin": "https://other.example"},
            ).status_code
            == 403
        )


def test_request_slot_limit_and_disconnect_release():
    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()
        responses = []

        async def downstream(scope, receive, send):
            entered.set()
            await release.wait()

        middleware = RequestLimits(downstream)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/workshop/references",
            "headers": [],
            "client": ("test", 1),
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            responses.append(message)

        first = asyncio.create_task(middleware(scope, receive, send))
        await entered.wait()
        entered.clear()
        second = asyncio.create_task(middleware(scope, receive, send))
        await entered.wait()
        await middleware(scope, receive, send)
        assert responses[0]["status"] == 429
        release.set()
        await asyncio.gather(first, second)

        async def disconnect():
            return {"type": "http.disconnect"}

        await middleware(scope, disconnect, send)
        assert middleware.uploads.acquire(blocking=False)
        assert middleware.uploads.acquire(blocking=False)
        middleware.uploads.release()
        middleware.uploads.release()

    asyncio.run(exercise())


def test_course_metadata_never_selects_file_blob():
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/auth/register",
                json={
                    "email": uuid4().hex + "@example.com",
                    "password": "secure-test-password",
                },
            ).status_code
            == 200
        )
        cid = client.post("/api/courses", json={"title": "metadata budget"}).json()[
            "id"
        ]
        # A failed source avoids parsing and exercises the normal details endpoint.
        with Session.begin() as db:
            db.add(
                SourceFile(
                    id=str(uuid4()),
                    course_id=cid,
                    name="private.pdf",
                    data=b"x" * 1024 * 1024,
                    status="failed",
                )
            )
        statements = []

        def capture(connection, cursor, statement, parameters, context, many):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture)
        try:
            response = client.get("/api/courses/" + cid)
            assert response.status_code == 200
            assert len(response.content) < 1024
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert not any("source_files.data" in statement for statement in statements)
