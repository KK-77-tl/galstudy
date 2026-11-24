import asyncio
import base64
import json
import time
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

rsa = pytest.importorskip("rsa")
from test_alipay_gateway import keys, envelope
from backend import main, payments, workshop
from backend.db import Session, Order, Entitlement, Refund
from backend.alipay_gateway import AlipayGateway
from backend.alipay_provider import AlipayPaymentProvider


@pytest.fixture
def api_clients(keys, monkeypatch):
    async def idle():
        await asyncio.Event().wait()
    monkeypatch.setattr(main, "worker", idle)
    monkeypatch.setattr(workshop, "worker", idle)
    control = {"queries": 0, "refund_calls": 0, "refund_success": False, "refund_timeout": False,
               "bad_amount": False, "query_failure": False, "trades": {}}
    def handler(request):
        params = dict(parse_qsl(request.content.decode()))
        signature = base64.b64decode(params.pop("sign"))
        content = "&".join(f"{k}={params[k]}" for k in sorted(params)).encode()
        assert rsa.verify(content, signature, keys[0]) == "SHA-256"
        biz = json.loads(params["biz_content"])
        oid = biz["out_trade_no"]
        trade = control["trades"].setdefault(oid, str(uuid4().int))
        method = params["method"]
        data = {"code": "10000", "out_trade_no": oid, "trade_no": trade, "total_amount": "9.90"}
        if method == "alipay.trade.query":
            control["queries"] += 1
            if control["query_failure"]:
                raise httpx.ReadTimeout("synthetic timeout")
            data["trade_status"] = "TRADE_SUCCESS"
            if control["bad_amount"]:
                data["total_amount"] = "0.01"
        elif method == "alipay.trade.refund":
            control["refund_calls"] += 1
            if control["refund_timeout"]:
                raise httpx.ReadTimeout("synthetic timeout after submit")
            data["refund_fee"] = biz["refund_amount"]
        else:
            assert method == "alipay.trade.fastpay.refund.query"
            if control["refund_success"]:
                data.update(refund_status="REFUND_SUCCESS", out_request_no=biz["out_request_no"], refund_amount="9.90")
        return httpx.Response(200, text=envelope(keys, method, json.dumps(data, ensure_ascii=False)))
    gateway = AlipayGateway("2026000000000001", keys[1].save_pkcs1(), keys[3], transport=httpx.MockTransport(handler))
    provider = AlipayPaymentProvider(gateway, "2088000000000001", "https://example.invalid", keys[3])
    monkeypatch.setattr(payments, "payment_provider", provider)
    with TestClient(main.app) as a, TestClient(main.app) as b:
        for client in (a, b):
            assert client.post("/api/auth/register", json={"email": str(uuid4()) + "@example.com", "password": "alipay-synthetic-pass"}).status_code == 200
        yield a, b, control, keys


def new_order(client):
    r = client.post("/api/workshop/orders", json={"request_id": str(uuid4())})
    assert r.status_code == 200
    assert r.json()["mode"] == "alipay_sandbox"
    assert r.json()["checkout"]["url"].startswith("https://openapi.alipaydev.com/")
    return r.json()["id"]


def notify_body(oid, trade, keys):
    p = {"app_id": "2026000000000001", "seller_id": "2088000000000001", "out_trade_no": oid,
         "trade_no": trade, "trade_status": "TRADE_SUCCESS", "total_amount": "9.90", "sign_type": "RSA2", "charset": "utf-8"}
    canonical = "&".join(f"{k}={p[k]}" for k in sorted(p) if k != "sign_type").encode()
    p["sign"] = base64.b64encode(rsa.sign(canonical, keys[2], "SHA-256")).decode()
    return urlencode(p)


def test_owned_query_grants_once_and_cannot_be_simulated(api_clients):
    a, b, control, _ = api_clients
    oid = new_order(a)
    assert b.post(f"/api/workshop/orders/{oid}/refresh").status_code == 404
    assert control["queries"] == 0
    assert a.post(f"/api/workshop/orders/{oid}/simulate", json={"status": "paid"}).status_code == 409
    path = f"/api/workshop/orders/{oid}/refresh"
    first = a.post(path)
    assert first.status_code == 200 and first.json()["status"] == "paid"
    assert a.post(path).json()["entitlement"]["id"] == first.json()["entitlement"]["id"]


def test_bad_query_never_grants_and_provider_failure_is_visible(api_clients):
    a, _, control, _ = api_clients
    oid = new_order(a)
    control["bad_amount"] = True
    assert a.post(f"/api/workshop/orders/{oid}/refresh").status_code == 502
    control["query_failure"] = True
    assert a.post(f"/api/workshop/orders/{oid}/refresh").status_code == 502
    assert a.get(f"/api/workshop/orders/{oid}").json()["entitlement"] is None


def test_signed_notice_requires_query_and_repeated_delivery_is_idempotent(api_clients):
    a, _, control, keys = api_clients
    oid = new_order(a)
    trade = str(uuid4().int)
    control["trades"][oid] = trade
    body = notify_body(oid, trade, keys)
    path = "/api/workshop/payments/alipay/notify"
    assert a.post(path, content=body.replace("9.90", "0.01"), headers={"Content-Type": "application/x-www-form-urlencoded"}).text == "failure"
    assert control["queries"] == 0
    for _ in range(2):
        r = a.post(path, content=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 200 and r.text == "success"
    assert control["queries"] == 2
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Entitlement).where(Entitlement.order_id == oid)) == 1


def test_notice_query_failure_and_body_limit_never_authorize(api_clients):
    a, _, control, keys = api_clients
    oid = new_order(a)
    trade = str(uuid4().int)
    control["trades"][oid] = trade
    control["query_failure"] = True
    body = notify_body(oid, trade, keys)
    r = a.post("/api/workshop/payments/alipay/notify", content=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 503 and r.text == "failure"
    assert a.post("/api/workshop/payments/alipay/notify", content=b"x" * 16385).status_code == 413
    assert a.get(f"/api/workshop/orders/{oid}").json()["entitlement"] is None


def test_refund_timeout_never_resubmits_then_verified_query_completes(api_clients):
    a, b, control, _ = api_clients
    oid = new_order(a)
    assert a.post(f"/api/workshop/orders/{oid}/refresh").status_code == 200
    control["refund_timeout"] = True
    r = a.post(f"/api/workshop/orders/{oid}/refund")
    assert r.status_code == 202 and r.json()["refund"]["status"] == "unknown"
    assert r.json()["entitlement"]["status"] == "refunding"
    rid = r.json()["refund"]["id"]
    assert a.post(f"/api/workshop/orders/{oid}/refund").status_code == 202
    assert control["refund_calls"] == 1
    assert b.post(f"/api/workshop/refunds/{rid}/refresh").status_code == 404
    assert a.post(f"/api/workshop/refunds/{rid}/refresh").status_code == 429
    with Session.begin() as db:
        db.get(Refund, rid).updated_at = int(time.time()) - 11
    assert a.post(f"/api/workshop/refunds/{rid}/refresh").json()["status"] == "refund_pending"
    control["refund_success"] = True
    with Session.begin() as db:
        db.get(Refund, rid).updated_at = int(time.time()) - 11
    final = a.post(f"/api/workshop/refunds/{rid}/refresh").json()
    assert final["status"] == "refunded" and final["entitlement"]["status"] == "refunded"
    assert a.post(f"/api/workshop/orders/{oid}/refresh").json()["status"] == "refunded"
    assert control["refund_calls"] == 1


def test_legacy_mock_order_stays_mock_after_mode_switch(api_clients):
    a, _, _, _ = api_clients
    oid = new_order(a)
    with Session.begin() as db:
        db.get(Order, oid).provider = "mock"
    view = a.get(f"/api/workshop/orders/{oid}").json()
    assert view["mode"] == view["checkout"]["mode"] == "mock"
    assert a.post(f"/api/workshop/orders/{oid}/refresh").status_code == 409


def test_restart_recovers_submission_as_unknown_without_repeating_money_request(api_clients):
    a, _, control, _ = api_clients
    oid = new_order(a)
    assert a.post(f"/api/workshop/orders/{oid}/refresh").status_code == 200
    r = a.post(f"/api/workshop/orders/{oid}/refund").json()
    rid = r["refund"]["id"]
    with Session.begin() as db:
        db.get(Refund, rid).status = "submitting"
    with TestClient(main.app):
        with Session() as db:
            assert db.get(Refund, rid).status == "unknown"
    assert a.post(f"/api/workshop/orders/{oid}/refund").json()["refund"]["status"] == "unknown"
    assert control["refund_calls"] == 1


def test_configured_sandbox_provider_boots_from_server_key_files(keys):
    directory = Path(os.environ["GALSTUDY_TEST_ROOT"]).resolve() / ("configured-pay-" + uuid4().hex)
    directory.mkdir()
    private = directory / "app-private.pem"
    public = directory / "alipay-public.pem"
    private.write_bytes(keys[1].save_pkcs1())
    public.write_text(keys[3], encoding="ascii")
    env = {**os.environ, "PAYMENT_PROVIDER": "alipay_sandbox", "ALIPAY_APP_ID": "2026000000000001",
           "ALIPAY_SELLER_ID": "2088000000000001", "ALIPAY_PRIVATE_KEY_PATH": str(private),
           "ALIPAY_PUBLIC_KEY_PATH": str(public), "APP_ORIGIN": "https://example.invalid",
           "DATABASE_URL": "sqlite:///" + (directory / "startup.db").as_posix()}
    code = """
from fastapi.testclient import TestClient
from backend import main, payments
assert payments.payment_provider.mode == 'alipay_sandbox'
with TestClient(main.app) as client:
    assert client.get('/api/health').status_code == 200
print('configured_sandbox_startup_ok')
"""
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "configured_sandbox_startup_ok" in result.stdout
