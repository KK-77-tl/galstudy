"""Alipay business adapter for the server-selected payment provider."""
from decimal import Decimal
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from .alipay_gateway import AlipayGateway, AlipayGatewayError
from .alipay_protocol import verify_notification


def cents(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?", value):
        raise AlipayGatewayError("支付宝金额格式无效")
    return int(Decimal(value) * 100)


class AlipayPaymentProvider:
    def __init__(self, gateway, seller_id, origin, alipay_public_key, *, sandbox=True):
        parsed = urlparse(origin)
        if (type(sandbox) is not bool or not re.fullmatch(r"[0-9]{16,30}", seller_id)
                or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
            raise ValueError("支付宝收款方或HTTPS站点配置无效")
        expected_gateway = "https://openapi.alipaydev.com/gateway.do" if sandbox else "https://openapi.alipay.com/gateway.do"
        if gateway.gateway != expected_gateway:
            raise ValueError("支付宝沙箱与正式网关配置不一致")
        self.gateway = gateway
        self.seller_id = seller_id
        self.origin = origin.rstrip("/")
        self.public_key = alipay_public_key
        self.mode = "alipay_sandbox" if sandbox else "alipay_live"

    def _order(self, order):
        if order.provider != self.mode or order.currency != "CNY":
            raise AlipayGatewayError("订单不属于当前支付宝支付环境")

    def checkout(self, order):
        self._order(order)
        return {
            "mode": self.mode, "order_id": order.id, "amount_cents": order.amount_cents, "currency": "CNY",
            "url": self.gateway.checkout_url(order.id, order.amount_cents, self.origin) if order.status == "pending" else None,
            "notice": "支付宝沙箱测试，不产生真实扣款。" if self.mode == "alipay_sandbox" else "支付宝付款，由支付宝页面确认金额。",
        }

    def verify_notice(self, body, order):
        self._order(order)
        try:
            return verify_notification(body, self.public_key, app_id=self.gateway.app_id,
                                       seller_id=self.seller_id, order_id=order.id, amount_cents=order.amount_cents)
        except ValueError as error:
            raise AlipayGatewayError("支付宝通知验签或订单核对失败") from error

    def _identity(self, data, order):
        if (data.get("out_trade_no") != order.id or data.get("app_id", self.gateway.app_id) != self.gateway.app_id
                or data.get("seller_id", self.seller_id) != self.seller_id):
            raise AlipayGatewayError("支付宝结果与应用、收款方或订单不匹配")
        trade = data.get("trade_no")
        if trade is not None and (not isinstance(trade, str) or not re.fullmatch(r"[0-9]{1,64}", trade)):
            raise AlipayGatewayError("支付宝交易号无效")
        if order.provider_trade_id and trade != order.provider_trade_id:
            raise AlipayGatewayError("支付宝交易号与订单不匹配")
        return trade

    async def query(self, order):
        from .payment_state import VerifiedPayment
        self._order(order)
        data = await self.gateway.query(order.id)
        trade = self._identity(data, order)
        if cents(data.get("total_amount")) != order.amount_cents:
            raise AlipayGatewayError("支付宝订单金额不匹配")
        status = {"WAIT_BUYER_PAY": "pending", "TRADE_SUCCESS": "paid", "TRADE_FINISHED": "paid", "TRADE_CLOSED": "closed"}.get(data.get("trade_status"))
        if status is None:
            raise AlipayGatewayError("支付宝交易状态未识别")
        if not trade:
            if status == "pending":
                return None
            raise AlipayGatewayError("支付宝未返回交易号，不能确认付款")
        return VerifiedPayment(event_id=f"query:{trade}:{status}", order_id=order.id, provider=self.mode,
                               trade_id=trade, amount_cents=order.amount_cents, status=status)

    async def submit_refund(self, order, refund):
        self._order(order)
        if refund.order_id != order.id or refund.amount_cents != order.amount_cents or not order.provider_trade_id:
            raise AlipayGatewayError("退款请求与订单不匹配")
        data = await self.gateway.refund(order.id, refund.amount_cents, refund.id)
        self._identity(data, order)
        if cents(data.get("refund_fee")) != refund.amount_cents:
            raise AlipayGatewayError("支付宝退款金额不匹配，须查询核对")
        # Completion is established by the fixed-ID refund query, not a browser
        # redirect or a bare code=10000 response. Caller persists unknown/pending.

    async def query_refund(self, order, refund):
        from .payment_state import VerifiedRefund
        self._order(order)
        if refund.order_id != order.id or refund.amount_cents != order.amount_cents:
            raise AlipayGatewayError("退款请求与订单不匹配")
        data = await self.gateway.query_refund(order.id, refund.id)
        if data.get("refund_status") != "REFUND_SUCCESS":
            # Absence can be temporary according to Alipay; do not unfreeze.
            return None
        trade = self._identity(data, order)
        if (not trade or data.get("out_request_no") != refund.id
                or cents(data.get("total_amount")) != order.amount_cents
                or cents(data.get("refund_amount")) != refund.amount_cents):
            raise AlipayGatewayError("支付宝退款查询与原请求不匹配")
        return VerifiedRefund(refund_id=refund.id, order_id=order.id, provider=self.mode,
                              trade_id=trade, amount_cents=refund.amount_cents)


def configured_alipay_provider(mode):
    if mode not in {"alipay_sandbox", "alipay_live"}:
        raise ValueError("支付宝模式无效")
    names = ["ALIPAY_APP_ID", "ALIPAY_SELLER_ID", "ALIPAY_PRIVATE_KEY_PATH", "ALIPAY_PUBLIC_KEY_PATH", "APP_ORIGIN"]
    values = {name: os.getenv(name, "") for name in names}
    if not all(values.values()):
        raise RuntimeError("支付宝配置不完整，需要应用、收款方、公私钥文件与HTTPS站点。")
    try:
        public = Path(values["ALIPAY_PUBLIC_KEY_PATH"]).read_bytes()
        gateway = AlipayGateway(values["ALIPAY_APP_ID"], Path(values["ALIPAY_PRIVATE_KEY_PATH"]).read_bytes(), public,
                                 sandbox=mode == "alipay_sandbox")
        return AlipayPaymentProvider(gateway, values["ALIPAY_SELLER_ID"], values["APP_ORIGIN"], public,
                                      sandbox=mode == "alipay_sandbox")
    except Exception as error:
        raise RuntimeError("支付宝密钥或环境配置无效，请核查服务端配置。") from error
