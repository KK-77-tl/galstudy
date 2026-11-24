"""Authenticated Alipay synchronization and refunds, plus signed provider notices."""
import time
from types import SimpleNamespace
from urllib.parse import parse_qsl
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from .db import Session, Order, Refund
from . import payments, workshop, payment_state
from .alipay_gateway import AlipayGatewayError


def database():
    with Session() as db:
        yield db


def provider_for(order):
    provider = payments.payment_provider
    if order.provider not in {"alipay_sandbox", "alipay_live"} or provider.mode != order.provider:
        raise HTTPException(409, "此订单的支付宝环境当前未启用")
    return provider


def snapshot(order):
    return SimpleNamespace(**{key: getattr(order, key) for key in
        ["id", "provider", "currency", "amount_cents", "provider_trade_id", "status"]})


def build_alipay_router(user_dependency):
    router = APIRouter()

    @router.post("/orders/{order_id}/refresh")
    async def refresh(order_id: str, current=Depends(user_dependency), db=Depends(database)):
        order = workshop.owned(db, Order, order_id, current.id)
        provider, saved = provider_for(order), snapshot(order)
        db.rollback()  # no transaction/row lock is held while awaiting Alipay
        try:
            receipt = await provider.query(saved)
        except AlipayGatewayError as error:
            raise HTTPException(502, "付款状态暂未确认，请稍后查询。") from error
        if receipt is not None:
            payment_state.accept_payment(db, receipt)
        return workshop.order_view(db, db.get(Order, order_id))

    @router.post("/payments/alipay/notify", response_class=PlainTextResponse)
    async def notify(request: Request, db=Depends(database)):
        if payments.payment_provider.mode not in {"alipay_sandbox", "alipay_live"}:
            return PlainTextResponse("failure", status_code=409)
        if not request.headers.get("content-type", "").lower().startswith("application/x-www-form-urlencoded"):
            return PlainTextResponse("failure", status_code=400)
        body = await request.body()
        try:
            if not 1 <= len(body) <= 16384:
                raise ValueError
            pairs = parse_qsl(body.decode("utf-8", errors="strict"), keep_blank_values=True,
                              strict_parsing=True, errors="strict", max_num_fields=128)
            values = dict(pairs)
            oid = values["out_trade_no"]
            if len(values) != len(pairs) or str(UUID(oid)) != oid:
                raise ValueError
            order = db.get(Order, oid)
            if not order:
                raise ValueError
            provider, saved = provider_for(order), snapshot(order)
            notice = provider.verify_notice(body, saved)
            db.rollback()
            receipt = await provider.query(saved)
            if receipt is None or receipt.status == "pending":
                return PlainTextResponse("failure", status_code=503)
            if receipt.trade_id != notice.trade_id:
                raise ValueError
            payment_state.accept_payment(db, receipt)
            return PlainTextResponse("success")
        except (ValueError, KeyError, HTTPException):
            db.rollback()
            return PlainTextResponse("failure", status_code=400)
        except AlipayGatewayError:
            db.rollback()
            return PlainTextResponse("failure", status_code=503)

    @router.post("/orders/{order_id}/refund", status_code=202)
    async def refund(order_id: str, current=Depends(user_dependency), db=Depends(database)):
        user_id = current.id
        order = workshop.owned(db, Order, order_id, user_id)
        provider = provider_for(order)
        db.rollback()
        record = payment_state.begin_refund(db, order_id, user_id)
        rid = record.id
        if payment_state.claim_refund(db, rid, user_id):
            saved_order = snapshot(db.get(Order, order_id))
            saved_refund = SimpleNamespace(id=rid, order_id=order_id, amount_cents=record.amount_cents)
            db.rollback()
            try:
                await provider.submit_refund(saved_order, saved_refund)
            except AlipayGatewayError:
                pass  # No retry: even a transport failure can hide a completed refund.
            payment_state.refund_unknown(db, rid, user_id)
        return workshop.order_view(db, db.get(Order, order_id))

    @router.post("/refunds/{refund_id}/refresh")
    async def refresh_refund(refund_id: str, current=Depends(user_dependency), db=Depends(database)):
        user_id = current.id
        record = workshop.owned(db, Refund, refund_id, user_id)
        order = db.get(Order, record.order_id)
        provider = provider_for(order)
        if record.status == "succeeded":
            return workshop.order_view(db, order)
        if time.time() - record.updated_at < 10:
            raise HTTPException(429, "退款处理中，请至少10秒后查询。")
        saved_order = snapshot(order)
        saved_refund = SimpleNamespace(id=record.id, order_id=record.order_id, amount_cents=record.amount_cents)
        db.rollback()
        try:
            proof = await provider.query_refund(saved_order, saved_refund)
        except AlipayGatewayError:
            proof = None
        if proof:
            payment_state.complete_refund(db, proof)
        else:
            payment_state.refund_unknown(db, refund_id, user_id)
        return workshop.order_view(db, db.get(Order, saved_order.id))

    return router
