"""Exercise the built UI under Chromium network throttling and real API failures."""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4

import httpx
import uvicorn
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
directory = ROOT / "test-results" / ("network-" + uuid4().hex)
directory.mkdir(parents=True)
os.environ.update({
    "DATABASE_URL": "sqlite:///" + (directory / "browser.db").as_posix(),
    "LLM_MODE": "demo", "LLM_CHAT_MODE": "demo", "IMAGE_GENERATOR": "mock",
    "PAYMENT_PROVIDER": "mock",
})
from backend import main, providers

control = {"slow_chat": False}


class DelayedDemo(providers.DemoLLMProvider):
    async def stream_chat(self, character, question, evidence, history):
        async for fragment in super().stream_chat(character, question, evidence, history):
            if control["slow_chat"]:
                await asyncio.sleep(0.5)
            yield fragment


providers.chat_provider = DelayedDemo()
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
    headers = [
        (key.encode(), value.encode())
        for key, value in response.headers.items()
        if key not in {"content-encoding", "content-length", "transfer-encoding", "connection"}
    ]
    await send({"type": "http.response.start", "status": response.status_code, "headers": headers})
    await send({"type": "http.response.body", "body": response.content})


NETWORK = {
    "offline": False,
    "latency": 300,
    "downloadThroughput": 200 * 1024,
    "uploadThroughput": 64 * 1024,
    "connectionType": "cellular3g",
}
report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(), "network": NETWORK, "cases": [], "real_model_calls": 0, "scratch_directory": str(directory)}
report_path = ROOT / "docs/network-result.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
server = uvicorn.Server(uvicorn.Config(fixture, log_level="error", access_log=False))
thread = threading.Thread(target=lambda: server.run(sockets=[listening]), daemon=True)
web_process = None


def exercise(browser, mobile):
    started = time.monotonic()
    context = browser.new_context(
        viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 1000},
        is_mobile=mobile, has_touch=mobile,
    )
    page = context.new_page()
    page.set_default_timeout(45000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions", NETWORK)

    def navigate(label):
        menu = page.get_by_role("button", name="打开导航", exact=True)
        if mobile and menu.is_visible():
            menu.click()
        page.get_by_role("button", name=label, exact=True).click()

    def return_to_story():
        navigate("我的课程")
        page.get_by_role("button", name="进入项目").click()
        page.get_by_role("button", name="继续剧情").click()

    page.goto(base + "/study", wait_until="domcontentloaded", timeout=90000)
    page.get_by_role("button", name="登录 / 注册").click()
    page.get_by_role("button", name="第一次来？创建账号").click()
    page.get_by_label("邮箱", exact=True).fill(uuid4().hex + "@example.com")
    page.get_by_label("密码", exact=True).fill("network-test-password-2026")
    page.get_by_role("button", name="创建账号", exact=True).click()
    page.get_by_role("button", name="新建学习项目").click()
    page.get_by_label("课程名称").fill("弱网学习验收")
    with page.expect_response(lambda response: response.url.endswith("/api/courses") and response.request.method == "POST") as created:
        page.get_by_role("button", name="创建学习项目", exact=True).click()
    course_id = created.value.json()["id"]
    expect(page.locator("input[type=file]")).to_be_enabled()
    cdp.send("Network.emulateNetworkConditions", {**NETWORK, "offline": True})
    page.locator("input[type=file]").set_input_files(str(ROOT / "tests/samples/original.pdf"))
    expect(page.locator(".notice[role=alert]")).to_be_visible()
    cdp.send("Network.emulateNetworkConditions", NETWORK)
    assert context.request.get(base + f"/api/courses/{course_id}").json()["files"] == []
    for index, extension in enumerate(["pdf", "pptx", "docx"], start=1):
        page.locator("input[type=file]").set_input_files(str(ROOT / f"tests/samples/original.{extension}"))
        expect(page.get_by_text("解析完成", exact=True)).to_have_count(index)
    point = page.get_by_role("textbox", name="知识点内容").first
    point.fill("检索练习需要合上书，主动回忆知识要点。")
    page.get_by_role("button", name="确认知识点").first.click()
    expect(page.get_by_text("已确认", exact=True)).to_be_visible()
    page.get_by_role("button", name="生成 Demo 剧情", exact=True).click()
    page.get_by_role("button", name="先和小栞梳理笔记").click()
    page.get_by_role("button", name="带上笔记，去图书馆").click()
    wrong = page.get_by_role("button", name="只要记住课程名称，就能推断资料中的所有结论。", exact=True)
    expect(wrong).to_be_visible()
    path = f"/api/courses/{course_id}/play"
    before = context.request.get(base + path).json()
    cdp.send("Network.emulateNetworkConditions", {**NETWORK, "offline": True})
    wrong.click()
    expect(page.locator(".notice[role=alert]")).to_be_visible()
    assert context.request.get(base + path).json() == before
    cdp.send("Network.emulateNetworkConditions", NETWORK)

    def lose_committed_response(route):
        response = route.fetch()
        assert response.status == 200
        route.abort("connectionreset")

    page.route("**" + path, lose_committed_response, times=1)
    wrong.click()
    expect(page.locator(".notice[role=alert]")).to_be_visible()
    saved = context.request.get(base + path).json()
    assert saved["node_id"] == "review" and saved["version"] == before["version"] + 1
    assert len(context.request.get(base + "/api/wrong-answers").json()) == 1
    page.reload(wait_until="domcontentloaded", timeout=90000)
    return_to_story()
    expect(page.get_by_text("结局 · 留给明天的书签", exact=False)).to_be_visible()
    assert context.request.get(base + path).json()["version"] == saved["version"]
    page.get_by_role("button", name="打开陪学伙伴", exact=True).click()
    question = page.get_by_label("向陪学伙伴提问", exact=True)
    expect(question).to_be_enabled()
    control["slow_chat"] = True
    question.fill("检索练习")
    page.get_by_role("button", name="发送陪学消息").click()
    reply = page.get_by_label("聊天记录", exact=True).locator("article").last.locator("p").first
    expect(reply).to_contain_text(re.compile("先|依据"))
    cdp.send("Network.emulateNetworkConditions", {**NETWORK, "offline": True})
    expect(page.get_by_role("alert").filter(has_text=re.compile("fetch|网络|中断|network", re.I))).to_be_visible()
    cdp.send("Network.emulateNetworkConditions", NETWORK)
    control["slow_chat"] = False
    expect(page.get_by_role("button", name="刷新会话")).to_be_enabled()
    with page.expect_response(
        lambda response: "/api/chat/sessions/" in response.url
        and response.request.method == "GET"
    ) as interrupted_response:
        page.get_by_role("button", name="刷新会话").click()
    interrupted = interrupted_response.value.json()
    interrupted_replies = [message for message in interrupted["messages"] if message["role"] == "assistant"]
    settled = time.monotonic() + 10
    while any(message["status"] == "processing" for message in interrupted_replies):
        if time.monotonic() > settled:
            raise RuntimeError("Interrupted Demo reply did not settle")
        page.wait_for_timeout(100)
        interrupted = context.request.get(base + "/api/chat/sessions/" + interrupted["id"]).json()
        interrupted_replies = [message for message in interrupted["messages"] if message["role"] == "assistant"]
    assert len(interrupted_replies) == 1
    assert interrupted_replies[0]["status"] in {"complete", "failed"}
    assert len(interrupted["messages"]) == 2
    expect(question).to_be_enabled()
    question.fill("检索练习的关键步骤是什么？")
    with page.expect_response(
        lambda response: "/api/chat/sessions/" in response.url
        and response.request.method == "GET"
    ) as recovered_response:
        page.get_by_role("button", name="发送陪学消息").click()
    recovered = recovered_response.value.json()
    replies = [message for message in recovered["messages"] if message["role"] == "assistant"]
    assert replies[0]["status"] == interrupted_replies[0]["status"]
    assert replies[-1]["status"] == "complete"
    assert "主动回忆知识要点" in replies[-1]["content"]
    assert len(recovered["messages"]) == 4
    expect(page.get_by_role("button", name="刷新会话")).to_be_enabled()
    expect(page.get_by_label("聊天记录", exact=True)).to_contain_text("主动回忆知识要点")
    page.get_by_role("button", name="收起陪学", exact=True).click()
    page.locator(".player-bg").evaluate("image => image.decode()")
    page.locator(".player-sprite").evaluate("image => image.decode()")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(ROOT / "docs" / ("network-mobile.png" if mobile else "network-desktop.png")), full_page=True)
    assert errors == [], errors
    report["cases"].append({
        "viewport": "390x844" if mobile else "1440x1000", "seconds": round(time.monotonic() - started, 2),
        "checks": ["offline upload leaves no file, online retry succeeds", "three uploads", "edit and confirm", "generate and grade", "offline before submit preserves save", "lost committed response saves once", "reload resumes committed ending", "stream disconnect shown", "chat refresh and new message", "no horizontal overflow"],
        "page_errors": errors,
        "saved_node": saved["node_id"],
        "saved_version_before": before["version"],
        "saved_version_after": saved["version"],
        "wrong_answers": 1,
        "chat_reply_statuses": [message["status"] for message in replies],
        "chat_message_count": len(recovered["messages"]),
    })
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    context.close()


try:
    with (directory / "next.log").open("wb") as log:
        web_process = subprocess.Popen([
            "node", str(ROOT / "frontend/node_modules/next/dist/bin/next"), "start", str(ROOT / "frontend"), "--hostname", "127.0.0.1", "--port", str(web_port),
        ], stdout=log, stderr=log, env={**os.environ, "NEXT_TELEMETRY_DISABLED": "1"})
        deadline = time.monotonic() + 30
        with httpx.Client(trust_env=False, timeout=1) as client:
            while True:
                if web_process.poll() is not None:
                    raise RuntimeError("Built frontend failed to start")
                try:
                    readiness = client.get(upstream + "/study")
                    report["frontend_readiness_status"] = readiness.status_code
                    if readiness.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Frontend readiness timeout")
                time.sleep(0.1)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Fixture startup failed")
            time.sleep(0.05)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=os.getenv("E2E_BROWSER", "msedge"), headless=True)
            report["browser"] = browser.version
            exercise(browser, mobile=False)
            exercise(browser, mobile=True)
            browser.close()
        report["status"] = "passed"
except BaseException as error:
    report["status"] = "failed"
    report["error"] = repr(error)
    raise
finally:
    server.should_exit = True
    if thread.is_alive():
        thread.join(timeout=15)
    listening.close()
    report["fixture_stopped"] = not thread.is_alive()
    if web_process is not None and web_process.poll() is None:
        web_process.terminate()
        web_process.wait(timeout=15)
    report["frontend_stopped"] = web_process is not None and web_process.poll() is not None
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
