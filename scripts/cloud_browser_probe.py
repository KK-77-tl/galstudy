"""Isolated UI/API integration with simulated model HTTP and a temporary DB."""

import json
import os
import re
import socket
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
directory = ROOT / "test-results" / ("cloud-browser-" + uuid4().hex)
directory.mkdir(parents=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (directory / "browser.db").as_posix()
test_ocr = os.getenv("E2E_OCR", "0") == "1"
if test_ocr:
    os.environ["OCR_MODE"] = "tesseract"
    os.environ["OCR_DATA_PATH"] = str(ROOT / "data/tessdata")
from backend import main
from test_learning import provider, transport_handler
from playwright.sync_api import sync_playwright, expect
import httpx
import uvicorn

control = {"fail_story": False, "fail_draft": False, "calls": 0}


def simulated_model(request):
    control["calls"] += 1
    payload = json.loads(request.content)
    content = json.loads(payload["messages"][1]["content"])
    if ("sources" in content and control["fail_draft"]) or (
        "confirmed_points" in content and control["fail_story"]
    ):
        return httpx.Response(402)
    return transport_handler(request)


main.llm_provider = provider(simulated_model)
listening = socket.socket()
listening.bind(("127.0.0.1", 0))
port = listening.getsockname()[1]
main.APP_ORIGIN = f"http://localhost:{port}"


async def fixture_app(scope, receive, send):
    if scope["type"] == "lifespan" or scope.get("path", "").startswith("/api/"):
        await main.app(scope, receive, send)
        return
    # Serve the built frontend on the same origin as the isolated API. Multipart
    # uploads then use the native browser network path and retain their file bytes.
    path = scope["raw_path"].decode() + "?" + scope["query_string"].decode()
    async with httpx.AsyncClient(
        base_url=os.getenv("E2E_BASE_URL", "http://localhost:3000"), trust_env=False
    ) as web:
        response = await web.get(path)
    headers = [
        (key.encode(), value.encode())
        for key, value in response.headers.items()
        if key
        not in {"content-encoding", "content-length", "transfer-encoding", "connection"}
    ]
    await send(
        {
            "type": "http.response.start",
            "status": response.status_code,
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": response.content})


server = uvicorn.Server(
    uvicorn.Config(fixture_app, log_level="error", access_log=False)
)
thread = threading.Thread(target=lambda: server.run(sockets=[listening]), daemon=True)
thread.start()
deadline = time.monotonic() + 15
while not server.started:
    if not thread.is_alive() or time.monotonic() > deadline:
        raise RuntimeError("Fixture API failed to start")
    time.sleep(0.05)

try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        page.goto(f"http://localhost:{port}/study")
        page.get_by_role("button", name="登录 / 注册").click()
        page.get_by_role("button", name="第一次来？创建账号").click()
        page.get_by_role("textbox", name="邮箱").fill(uuid4().hex + "@example.com")
        page.get_by_label("密码", exact=True).fill("cloud-browser-test-password")
        page.get_by_role("button", name="创建账号", exact=True).click()
        page.get_by_role("button", name="新建学习项目").click()
        page.get_by_label("课程名称").fill("云端协议模拟验收")
        page.get_by_role("button", name="创建学习项目", exact=True).click()
        expect(page.locator("input[type=file]")).to_be_enabled()
        page.locator("input[type=file]").set_input_files(
            str(ROOT / "tests/samples/original.pdf")
        )
        try:
            expect(page.get_by_text("解析完成", exact=True)).to_be_visible(
                timeout=20000
            )
        except AssertionError:
            page.screenshot(path=str(directory / "failure.png"), full_page=True)
            print(page.locator(".notice").all_text_contents(), flush=True)
            raise
        expect(page.locator(".point-meta").first).to_contain_text("云端草稿")
        expect(page.locator(".file-row").first).to_contain_text("云端提炼")
        page.get_by_role("button", name="确认知识点").first.click()
        page.get_by_role("button", name="生成云端剧情", exact=True).click()
        expect(page.locator(".player-heading")).to_contain_text("云端剧情")
        page.get_by_role("button", name="先和小栞梳理笔记").click()
        page.get_by_role("button", name="带上笔记，去图书馆").click()
        page.locator(".player-bg").evaluate("image => image.decode()")
        page.locator(".player-sprite").evaluate("image => image.decode()")
        page.screenshot(
            path=str(ROOT / "docs/cloud-fixture-desktop.png"), full_page=True
        )
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(
            path=str(ROOT / "docs/cloud-fixture-mobile.png"), full_page=True
        )
        page.get_by_role("button", name=re.compile("^课程定义")).click()
        expect(page.locator(".player-heading")).to_contain_text("答对 1")
        page.get_by_role("button", name="返回项目", exact=True).click()
        control["fail_story"] = True
        page.get_by_role("button", name="生成新版本", exact=True).click()
        expect(page.locator(".notice[role=alert]")).to_contain_text("模型额度不足")
        calls = control["calls"]
        page.get_by_role("button", name="使用 Demo 模板", exact=True).click()
        expect(page.locator(".notice[role=alert]")).to_contain_text("Demo剧情版本 2")
        assert control["calls"] == calls
        if test_ocr:
            control["fail_draft"] = False
            expect(page.locator("input[type=file]")).to_be_enabled()
            page.locator("input[type=file]").set_input_files(
                str(ROOT / "tests/samples/original-scan.pdf")
            )
            scanned = page.locator(".file-row").filter(has_text="original-scan.pdf")
            expect(scanned).to_contain_text("解析完成", timeout=25000)
            point = page.locator(".point").filter(has_text="第 1 页 · OCR")
            expect(point.get_by_role("textbox", name="知识点内容")).to_have_value(
                re.compile("检索练习")
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(ROOT / "docs/ocr-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.screenshot(path=str(ROOT / "docs/ocr-desktop.png"), full_page=True)
        control["fail_draft"] = True
        expect(page.locator("input[type=file]")).to_be_enabled()
        page.locator("input[type=file]").set_input_files(
            str(ROOT / "tests/samples/original.docx")
        )
        failed = page.locator(".file-row").filter(has_text="original.docx")
        expect(failed).to_contain_text("解析失败", timeout=20000)
        calls = control["calls"]
        page.get_by_role("button", name="使用 Demo 摘录重试", exact=True).click()
        expect(failed).to_contain_text("解析完成", timeout=20000)
        expect(failed).to_contain_text("Demo摘录")
        assert control["calls"] == calls
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        report = {
            "status": "passed",
            "browser": browser.version,
            "model_transport": "httpx.MockTransport, original Demo graph used as structured response fixture",
            "real_model_calls": 0,
            "real_local_ocr": test_ocr,
            "simulated_model_calls": control["calls"],
            "database": "isolated test-results database",
            "api_routing": "Ephemeral same-origin fixture serves the built Next.js pages and isolated API",
            "checks": [
                "cloud upload and provenance",
                "confirmed knowledge to validated cloud-mode story",
                "desktop and 390px mobile layout",
                "server grading",
                "model failure shown",
                "explicit Demo story without another model call",
                "failed extraction then explicit Demo retry",
                "no page errors",
            ],
        }
        if test_ocr:
            report["checks"].append("image-only scan recognized locally with OCR source marker and editable knowledge on mobile and desktop")
        (ROOT / "docs/cloud-browser-result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        browser.close()
        print(json.dumps(report, ensure_ascii=False, indent=2))
finally:
    server.should_exit = True
    thread.join(timeout=10)
    listening.close()
    assert not thread.is_alive(), "Fixture API did not stop"
