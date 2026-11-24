"""Server-selected Mock or Alipay provider; orders retain their own mode."""

import hashlib
import hmac
import json
import os
import secrets
import re
from pathlib import Path
from typing import Protocol
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class PaymentNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=100)
    order_id: str = Field(min_length=36, max_length=36)
    amount_cents: int = Field(strict=True, gt=0)
    currency: Literal["CNY"]
    status: Literal["paid", "failed"]
    trade_id: str = Field(min_length=1, max_length=100)
    mode: Literal["mock"]


class PaymentProvider(Protocol):
    mode: str

    def checkout(self, order) -> dict: ...


class MockPaymentProvider:
    mode = "mock"

    def __init__(self, secret: bytes):
        self.secret = secret

    def checkout(self, order):
        return {
            "mode": "mock",
            "order_id": order.id,
            "amount_cents": order.amount_cents,
            "currency": order.currency,
            "notice": "模拟付款，不产生真实扣款。",
        }

    def sign(self, body):
        return hmac.new(self.secret, body, hashlib.sha256).hexdigest()

    def verify(self, body, signature):
        if not re.fullmatch(r"[0-9a-f]{64}", signature):
            return False
        return hmac.compare_digest(self.sign(body), signature)


def configured_mock_provider():
    secret = os.getenv("PAYMENT_MOCK_SECRET", "").encode()
    if not secret:
        path = Path("data/mock-payment.key")
        path.parent.mkdir(exist_ok=True)
        try:
            with path.open("xb") as file:
                file.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
        secret = path.read_bytes()
    return MockPaymentProvider(secret)


mock_payment_provider = configured_mock_provider()


def configured_payment_provider():
    mode = os.getenv("PAYMENT_PROVIDER", "mock")
    if mode == "mock":
        return mock_payment_provider
    if mode in {"alipay_sandbox", "alipay_live"}:
        if mode == "alipay_live" and os.getenv("IMAGE_GENERATOR", "mock") != "comfyui":
            raise RuntimeError("正式角色收款需要配置真实角色生成服务。")
        from .alipay_provider import configured_alipay_provider
        return configured_alipay_provider(mode)
    raise RuntimeError("未知的付款Provider配置")


payment_provider = configured_payment_provider()


def checkout_for(order):
    if order.provider == "mock":
        return mock_payment_provider.checkout(order)
    if order.provider == payment_provider.mode:
        return payment_provider.checkout(order)
    return {"mode": order.provider, "order_id": order.id, "amount_cents": order.amount_cents,
            "currency": order.currency, "url": None, "notice": "此订单的支付环境当前未启用。"}


def notification_body(order, status, event_id, trade_id):
    return json.dumps(
        {
            "event_id": event_id,
            "order_id": order.id,
            "amount_cents": order.amount_cents,
            "currency": order.currency,
            "status": status,
            "trade_id": trade_id,
            "mode": "mock",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
