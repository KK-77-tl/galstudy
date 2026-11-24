"""Isolated Demo/Mock regression in an additional installed browser engine."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument("engine", choices=["webkit", "firefox"])
engine = parser.parse_args().engine
directory = ROOT / "test-results" / (engine + "-" + uuid4().hex)
directory.mkdir(parents=True)
artifacts = ROOT / "docs" / engine
artifacts.mkdir(exist_ok=True)
os.environ.update({"DATABASE_URL": "sqlite:///" + (directory / "test.db").as_posix(),
                   "LLM_MODE": "demo", "LLM_CHAT_MODE": "demo", "IMAGE_GENERATOR": "mock", "PAYMENT_PROVIDER": "mock"})
from backend import main

listening = socket.socket()
listening.bind(("127.0.0.1", 0))
base = f"http://localhost:{listening.getsockname()[1]}"
main.APP_ORIGIN = base
with socket.socket() as available:
    available.bind(("127.0.0.1", 0))
    web_port = available.getsockname()[1]
upstream = f"http://127.0.0.1:{web_port}"

async def fixture(scope, receive, send):
    if scope["type"] == "lifespan" or scope.get("path", "").startswith("/api/"):
        await main.app(scope, receive, send)
        return
    path = scope["raw_path"].decode() + "?" + scope["query_string"].decode()
    async with httpx.AsyncClient(base_url=upstream, trust_env=False, timeout=30) as client:
        response = await client.get(path)
    headers = [(k.encode(), v.encode()) for k, v in response.headers.items()
               if k not in {"content-encoding", "content-length", "transfer-encoding", "connection"}]
    await send({"type": "http.response.start", "status": response.status_code, "headers": headers})
    await send({"type": "http.response.body", "body": response.content})

server = uvicorn.Server(uvicorn.Config(fixture, log_level="error", access_log=False))
thread = threading.Thread(target=lambda: server.run(sockets=[listening]), daemon=True)
web = None
report = {"status": "running", "engine": engine, "real_model_calls": 0, "directory": str(directory), "scope": "learning page, desktop and 390px viewport; no physical device or intro verification"}
try:
    with (directory / "next.log").open("wb") as log:
        web = subprocess.Popen(["node", str(ROOT / "frontend/node_modules/next/dist/bin/next"), "start", str(ROOT / "frontend"), "--hostname", "127.0.0.1", "--port", str(web_port)], stdout=log, stderr=log, env={**os.environ, "NEXT_TELEMETRY_DISABLED": "1"})
        deadline = time.monotonic() + 30
        with httpx.Client(trust_env=False, timeout=1) as client:
            while True:
                if web.poll() is not None:
                    raise RuntimeError("Frontend stopped during startup")
                try:
                    if client.get(upstream + "/study").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Frontend startup timeout")
                time.sleep(0.1)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Fixture startup failed")
            time.sleep(0.05)
        env = {**os.environ, "E2E_BASE_URL": base, "E2E_BROWSER": engine, "E2E_ARTIFACTS_DIR": str(artifacts), "E2E_DIRECT_STUDY": "1", "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / "data/playwright-browsers")}
        with (directory / "e2e.log").open("wb") as output:
            result = subprocess.run([sys.executable, str(ROOT / "scripts/e2e.py")], env=env, stdout=output, stderr=subprocess.STDOUT, timeout=240)
        report["exit_code"] = result.returncode
        if result.returncode:
            raise RuntimeError("E2E failed; inspect " + str(directory / "e2e.log"))
        report["status"] = "passed"
except BaseException as e:
    report["status"] = "failed"
    report["error"] = str(e)
    raise
finally:
    server.should_exit = True
    if thread.is_alive():
        thread.join(timeout=15)
    listening.close()
    if web is not None and web.poll() is None:
        web.terminate()
        web.wait(timeout=15)
    report["fixture_stopped"] = not thread.is_alive()
    report["frontend_stopped"] = web is not None and web.poll() is not None
    (artifacts / "runner-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
