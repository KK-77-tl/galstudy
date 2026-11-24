"""Transactional application of server-verified payment and refund receipts.

No HTTP route accepts these receipts. An Alipay adapter must verify/query the
provider and bind app/payee before calling this layer; browser returns cannot.
"""
import hashlib
import json
import time
from uuid import uuid4
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import Order, Entitlement, PaymentEvent, Refund
from .workshop import lock_user, owned


class VerifiedPayment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event_id: str = Field(min_length=1, max_length=128)
    order_id: str = Field(min_length=36, max_length=36)
    provider: Literal["alipay_sandbox", "alipay_live"]
    trade_id: str = Field(pattern=r"^[0-9]{1,64}$")
    amount_cents: int = Field(gt=0)
    currency: Literal["CNY"] = "CNY"
    status: Literal["pending", "paid", "closed"]


class VerifiedRefund(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    refund_id: str = Field(min_length=36, max_length=36)
    order_id: str = Field(min_length=36, max_length=36)
    provider: Literal["alipay_sandbox", "alipay_live"]
    trade_id: str = Field(pattern=r"^[0-9]{1,64}$")
    amount_cents: int = Field(gt=0)


def _commit(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "支付或退款记录已被并发请求占用，请刷新核对。") from error


def accept_payment(db, receipt: VerifiedPayment):
    order = db.get(Order, receipt.order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    lock_user(db, order.user_id)
    db.refresh(order)
    if order.provider != receipt.provider or order.currency != receipt.currency or order.amount_cents != receipt.amount_cents:
        raise HTTPException(400, "支付环境、金额或币种与订单不匹配")
    if order.provider_trade_id and order.provider_trade_id != receipt.trade_id:
        raise HTTPException(409, "支付交易与订单不匹配")
    canonical = json.dumps(receipt.model_dump(), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    event_id = hashlib.sha256((receipt.provider + ":" + receipt.event_id).encode()).hexdigest()
    previous = db.get(PaymentEvent, event_id)
    if previous:
        if previous.order_id != order.id or previous.digest != digest:
            raise HTTPException(409, "支付事件编号已用于其他内容")
        db.commit()
        return {"duplicate": True, "status": order.status}
    # Bind the transaction even for a pending receipt; the partial unique index
    # prevents one provider transaction from funding two users' orders.
    entitlement = db.scalar(select(Entitlement).where(Entitlement.order_id == order.id))
    order.provider_trade_id = receipt.trade_id
    protected = order.status in {"refund_pending", "refunded", "closed", "payment_review"}
    if receipt.status == "paid" and not protected:
        order.status = "paid"
        if entitlement is None:
            db.add(Entitlement(id=str(uuid4()), order_id=order.id, user_id=order.user_id, status="available"))
    elif receipt.status == "closed" and order.status == "paid":
        order.status = "payment_review"
        if entitlement and entitlement.status in {"available", "reserved"}:
            entitlement.status = "held"
    elif receipt.status == "closed" and order.status not in {"refund_pending", "refunded", "payment_review"}:
        order.status = "closed"
    db.add(PaymentEvent(id=event_id, order_id=order.id, digest=digest, status=receipt.status, created_at=int(time.time())))
    _commit(db)
    return {"duplicate": False, "status": order.status}


def begin_refund(db, order_id, user_id):
    lock_user(db, user_id)
    order = owned(db, Order, order_id, user_id)
    if order.provider not in {"alipay_sandbox", "alipay_live"}:
        raise HTTPException(409, "此操作仅适用于支付宝订单")
    previous = db.scalar(select(Refund).where(Refund.order_id == order.id))
    if previous:
        db.commit()
        return previous
    entitlement = db.scalar(select(Entitlement).where(Entitlement.order_id == order.id))
    if order.status != "paid" or not entitlement or entitlement.status != "available" or entitlement.reservation_job_id:
        raise HTTPException(409, "当前权益已使用或正在生成，需人工核对退款。")
    now = int(time.time())
    refund = Refund(id=str(uuid4()), order_id=order.id, user_id=user_id,
                    amount_cents=order.amount_cents, status="pending", created_at=now, updated_at=now)
    order.status = "refund_pending"
    entitlement.status = "refunding"
    db.add(refund)
    _commit(db)
    return refund


def refund_unknown(db, refund_id, user_id):
    lock_user(db, user_id)
    refund = owned(db, Refund, refund_id, user_id)
    if refund.status != "succeeded":
        refund.status = "unknown"
        refund.updated_at = int(time.time())
    db.commit()
    return refund


def claim_refund(db, refund_id, user_id):
    lock_user(db, user_id)
    refund = owned(db, Refund, refund_id, user_id)
    if refund.status != "pending":
        db.commit()
        return False
    order = db.get(Order, refund.order_id)
    entitlement = db.scalar(select(Entitlement).where(Entitlement.order_id == order.id))
    if order.status != "refund_pending" or not entitlement or entitlement.status != "refunding":
        raise HTTPException(409, "退款与权益状态需要核对")
    refund.status = "submitting"
    refund.updated_at = int(time.time())
    _commit(db)
    return True


def complete_refund(db, receipt: VerifiedRefund):
    refund = db.get(Refund, receipt.refund_id)
    if not refund:
        raise HTTPException(404, "退款请求不存在")
    lock_user(db, refund.user_id)
    db.refresh(refund)
    order = db.get(Order, refund.order_id)
    if (refund.order_id != receipt.order_id or order.provider != receipt.provider
            or order.provider_trade_id != receipt.trade_id or refund.amount_cents != receipt.amount_cents
            or order.amount_cents != receipt.amount_cents or order.currency != "CNY"):
        raise HTTPException(400, "退款凭据与订单不匹配")
    entitlement = db.scalar(select(Entitlement).where(Entitlement.order_id == order.id))
    if refund.status == "succeeded":
        db.commit()
        return refund
    if order.status != "refund_pending" or not entitlement or entitlement.status != "refunding":
        raise HTTPException(409, "退款与权益状态需要人工核对")
    refund.status = "succeeded"
    refund.updated_at = int(time.time())
    order.status = "refunded"
    entitlement.status = "refunded"
    _commit(db)
    return refund
