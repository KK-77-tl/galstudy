import asyncio
from types import SimpleNamespace
from uuid import uuid4
import pytest
from backend.alipay_gateway import AlipayGatewayError
from backend.alipay_provider import AlipayPaymentProvider, configured_alipay_provider


class Gateway:
    gateway = "https://openapi.alipaydev.com/gateway.do"
    app_id = "2026000000000001"
    def __init__(self, result):
        self.result = result
        self.calls = []
    def checkout_url(self, *args):
        self.calls.append(("checkout", args))
        return "https://openapi.alipaydev.com/gateway.do?synthetic"
    async def query(self, oid):
        self.calls.append(("query", oid))
        return self.result
    async def refund(self, *args):
        self.calls.append(("refund", args))
        return self.result
    async def query_refund(self, *args):
        self.calls.append(("query_refund", args))
        return self.result


@pytest.fixture
def order():
    return SimpleNamespace(id=str(uuid4()), provider="alipay_sandbox", currency="CNY", amount_cents=990,
                           provider_trade_id=None, status="pending")


def provider(result):
    return AlipayPaymentProvider(Gateway(result), "2088000000000001", "https://example.invalid", b"synthetic")


def result(order, **changes):
    return {"out_trade_no": order.id, "trade_no": "2026000000000001", "total_amount": "9.90",
            "trade_status": "TRADE_SUCCESS", **changes}


def test_checkout_does_not_relabel_historical_orders(order):
    p = provider({})
    assert p.checkout(order)["mode"] == "alipay_sandbox"
    order.provider = "mock"
    with pytest.raises(AlipayGatewayError):
        p.checkout(order)


@pytest.mark.parametrize("change", [{"out_trade_no": str(uuid4())}, {"total_amount": "0.01"},
                                   {"seller_id": "2088000000000002"}, {"app_id": "2026000000000002"},
                                   {"trade_status": "UNKNOWN"}, {"trade_no": None}])
def test_signed_but_mismatched_query_does_not_issue_receipt(order, change):
    with pytest.raises(AlipayGatewayError):
        asyncio.run(provider(result(order, **change)).query(order))


def test_waiting_trade_without_final_trade_id_is_not_payment(order):
    assert asyncio.run(provider(result(order, trade_no=None, trade_status="WAIT_BUYER_PAY")).query(order)) is None


def test_valid_query_receipt_is_bound_and_idempotent(order):
    p = provider(result(order))
    a, b = asyncio.run(p.query(order)), asyncio.run(p.query(order))
    assert a == b and a.status == "paid" and a.amount_cents == 990 and a.order_id == order.id
    order.provider_trade_id = "2026000000000002"
    with pytest.raises(AlipayGatewayError):
        asyncio.run(p.query(order))


def test_missing_refund_status_keeps_result_unknown(order):
    refund = SimpleNamespace(id=str(uuid4()), order_id=order.id, amount_cents=990)
    assert asyncio.run(provider({"code": "10000"}).query_refund(order, refund)) is None


@pytest.mark.parametrize("change", [{"out_request_no": str(uuid4())}, {"refund_amount": "0.01"}, {"total_amount": "10.00"}])
def test_refund_success_must_match_fixed_request(order, change):
    refund = SimpleNamespace(id=str(uuid4()), order_id=order.id, amount_cents=990)
    data = result(order, refund_status="REFUND_SUCCESS", out_request_no=refund.id, refund_amount="9.90")
    data.update(change)
    with pytest.raises(AlipayGatewayError):
        asyncio.run(provider(data).query_refund(order, refund))


def test_successful_refund_query_and_submission_keep_same_id(order):
    refund = SimpleNamespace(id=str(uuid4()), order_id=order.id, amount_cents=990)
    order.provider_trade_id = "2026000000000001"
    data = result(order, refund_status="REFUND_SUCCESS", out_request_no=refund.id, refund_amount="9.90", refund_fee="9.90")
    p = provider(data)
    asyncio.run(p.submit_refund(order, refund))
    receipt = asyncio.run(p.query_refund(order, refund))
    assert receipt.refund_id == refund.id
    assert p.gateway.calls[0][1][-1] == p.gateway.calls[1][1][-1] == refund.id


def test_missing_configuration_is_explicit(monkeypatch):
    monkeypatch.delenv("ALIPAY_APP_ID", raising=False)
    with pytest.raises(RuntimeError, match="配置不完整"):
        configured_alipay_provider("alipay_live")
    with pytest.raises(ValueError):
        AlipayPaymentProvider(Gateway({}), "2088000000000001", "https://example.invalid", b"key", sandbox=False)
