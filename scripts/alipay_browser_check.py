"""Built UI + real app routes, with a local synthetic Alipay gateway (no rail calls)."""
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
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
directory = ROOT / "test-results" / ("alipay-ui-" + uuid4().hex)
directory.mkdir(parents=True)
artifacts = ROOT / "docs/alipay-ui"
artifacts.mkdir(exist_ok=True)
os.environ.update({"DATABASE_URL": "sqlite:///" + (directory / "test.db").as_posix(), "PAYMENT_PROVIDER": "mock",
                   "LLM_MODE": "demo", "LLM_CHAT_MODE": "demo", "IMAGE_GENERATOR": "mock"})
from backend import main, payments
from backend.db import Session, Refund
from sqlalchemy import select
from backend.alipay_provider import AlipayPaymentProvider
from backend.alipay_gateway import AlipayOutcomeUnknown


class LocalBank:
    gateway = "https://openapi.alipaydev.com/gateway.do"
    app_id = "2026000000000001"
    def __init__(self):
        self.submits = 0
        self.confirmed = set()
    def checkout_url(self, *args):
        return self.gateway + "?method=alipay.trade.page.pay&synthetic=1"
    async def query(self, oid):
        return {"code": "10000", "out_trade_no": oid, "trade_no": str(int(UUID(oid))),
                "trade_status": "TRADE_SUCCESS", "total_amount": "9.90"}
    async def refund(self, *args):
        self.submits += 1
        raise AlipayOutcomeUnknown("Synthetic response loss")
    async def query_refund(self, oid, rid):
        data = {"code": "10000"}
        if rid in self.confirmed:
            data.update(out_trade_no=oid, trade_no=str(int(UUID(oid))), out_request_no=rid,
                        total_amount="9.90", refund_amount="9.90", refund_status="REFUND_SUCCESS")
        return data

from uuid import UUID
bank = LocalBank()
payments.payment_provider = AlipayPaymentProvider(bank, "2088000000000001", "https://example.invalid", b"not-used-by-ui-test")
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
base = f"http://localhost:{listener.getsockname()[1]}"
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
        r = await client.get(path)
    headers = [(k.encode(), v.encode()) for k, v in r.headers.items()
               if k not in {"content-encoding", "content-length", "transfer-encoding", "connection"}]
    await send({"type": "http.response.start", "status": r.status_code, "headers": headers})
    await send({"type": "http.response.body", "body": r.content})


server = uvicorn.Server(uvicorn.Config(fixture, log_level="error", access_log=False))
thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
web = None
report = {"status": "running", "gateway": "local synthetic fixture, not Alipay remote sandbox", "real_transactions": 0, "cases": []}
try:
    with (directory / "next.log").open("wb") as output:
        web = subprocess.Popen(["node", str(ROOT / "frontend/node_modules/next/dist/bin/next"), "start", str(ROOT / "frontend"), "--hostname", "127.0.0.1", "--port", str(web_port)], stdout=output, stderr=output)
        deadline = time.monotonic() + 30
        with httpx.Client(trust_env=False, timeout=1) as client:
            while True:
                if web.poll() is not None:
                    raise RuntimeError("Frontend stopped")
                try:
                    if client.get(upstream + "/study").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Frontend startup timed out")
                time.sleep(0.1)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("API startup timed out")
            time.sleep(0.05)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            for mobile in (False, True):
                name = "mobile" if mobile else "desktop"
                context = browser.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 1000})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/study")
                page.get_by_role("button", name="登录 / 注册").click()
                page.get_by_role("button", name="第一次来？创建账号").click()
                page.get_by_label("邮箱", exact=True).fill(uuid4().hex + "@example.com")
                page.get_by_label("密码", exact=True).fill("synthetic-alipay-ui-pass")
                page.get_by_role("button", name="创建账号", exact=True).click()
                expect(page.get_by_role("heading", name="我的课程", exact=True)).to_be_visible()
                if mobile:
                    page.get_by_role("button", name="打开导航").click()
                page.get_by_role("button", name="角色工坊", exact=True).click()
                expect(page.get_by_text("当前新订单使用支付宝沙箱", exact=False)).to_be_visible()
                page.get_by_role("button", name="创建订单", exact=True).click()
                pay_link = page.get_by_role("link", name="前往支付宝沙箱", exact=True)
                expect(pay_link).to_be_visible()
                assert pay_link.get_attribute("href").startswith(bank.gateway)
                assert page.get_by_role("button", name="模拟付款成功").count() == 0
                page.screenshot(path=str(artifacts / (name + "-pending.png")), full_page=True)
                page.get_by_role("button", name="查询付款状态", exact=True).click()
                expect(page.get_by_role("button", name="申请全额退款", exact=True)).to_be_visible()
                page.get_by_role("button", name="申请全额退款", exact=True).click()
                expect(page.locator("span").filter(has_text="退款冻结中")).to_be_visible()
                with Session.begin() as db:
                    refund = db.scalar(select(Refund).where(Refund.status == "unknown"))
                    rid = refund.id
                    refund.updated_at = int(time.time()) - 11
                bank.confirmed.add(rid)
                page.get_by_role("button", name="查询退款状态", exact=True).click()
                expect(page.locator("span").filter(has_text="已退款")).to_be_visible()
                expect(page.get_by_role("button", name="查询退款状态", exact=True)).to_have_count(0)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors, errors
                page.screenshot(path=str(artifacts / (name + "-refunded.png")), full_page=True)
                report["cases"].append({"name": name, "page_errors": errors, "checks": ["sandbox label", "matching payment link without navigation", "no mock simulation buttons", "payment query", "refund freezes entitlement", "verified refund query", "no overflow"]})
                context.close()
            browser.close()
        assert bank.submits == 2
        report.update(status="passed", synthetic_refund_submits=bank.submits)
except BaseException as error:
    report.update(status="failed", error=repr(error))
    raise
finally:
    server.should_exit = True
    if thread.is_alive():
        thread.join(timeout=15)
    listener.close()
    if web is not None and web.poll() is None:
        web.terminate()
        web.wait(timeout=15)
    report.update(fixture_stopped=not thread.is_alive(), frontend_stopped=web is not None and web.poll() is not None, directory=str(directory))
    (artifacts / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
