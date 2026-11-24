from concurrent.futures import ThreadPoolExecutor
import time
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.db import Session, migrate, User, Order, Entitlement, Refund
from backend import workshop
from backend.payment_state import VerifiedPayment, VerifiedRefund, accept_payment, begin_refund, refund_unknown, complete_refund, claim_refund


@pytest.fixture
def orders():
    migrate()
    workshop.seed_product()
    result = []
    with Session.begin() as db:
        for _ in range(2):
            user = str(uuid4())
            db.add(User(id=user, email=user + "@example.com", password="unusable-synthetic-password"))
            db.flush()
            order = Order(id=str(uuid4()), user_id=user, request_id=str(uuid4()), product_id=workshop.SKU,
                          amount_cents=990, pack_spec="{}", currency="CNY", provider="alipay_sandbox",
                          status="pending", created_at=int(time.time()))
            db.add(order)
            result.append((order.id, user))
    return result


def receipt(oid, **extra):
    values = {"event_id": str(uuid4()), "order_id": oid, "provider": "alipay_sandbox", "trade_id": str(uuid4().int),
              "amount_cents": 990, "status": "paid"}
    values.update(extra)
    return VerifiedPayment(**values)


def pay(event):
    with Session() as db:
        return accept_payment(db, event)


def test_duplicate_and_new_event_issue_one_entitlement(orders):
    event = receipt(orders[0][0])
    assert pay(event)["status"] == "paid"
    assert pay(event)["duplicate"]
    assert not pay(event.model_copy(update={"event_id": str(uuid4())}))["duplicate"]
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Entitlement).where(Entitlement.order_id == event.order_id)) == 1


@pytest.mark.parametrize("changed", [{"amount_cents": 1}, {"provider": "alipay_live"}])
def test_wrong_amount_or_environment_never_authorizes(orders, changed):
    with pytest.raises(HTTPException) as error:
        pay(receipt(orders[0][0], **changed))
    assert error.value.status_code == 400
    with Session() as db:
        assert not db.scalar(select(Entitlement).where(Entitlement.order_id == orders[0][0]))


def test_one_trade_cannot_pay_two_users_even_concurrently(orders):
    first = receipt(orders[0][0])
    second = receipt(orders[1][0], trade_id=first.trade_id)
    def attempt(event):
        try:
            pay(event)
            return 200
        except HTTPException as e:
            return e.status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(attempt, [first, second])) == [200, 409]
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Entitlement).where(Entitlement.order_id.in_([x[0] for x in orders]))) == 1


def test_refund_freezes_entitlement_until_verified_success_and_late_pay_does_not_regrant(orders):
    oid, uid = orders[0]
    event = receipt(oid)
    pay(event)
    with Session() as db:
        refund = begin_refund(db, oid, uid)
        rid = refund.id
        assert begin_refund(db, oid, uid).id == rid
        assert db.scalar(select(Entitlement).where(Entitlement.order_id == oid)).status == "refunding"
        db.rollback()
        assert refund_unknown(db, rid, uid).status == "unknown"
    assert pay(event.model_copy(update={"event_id": str(uuid4())}))["status"] == "refund_pending"
    proof = VerifiedRefund(refund_id=rid, order_id=oid, provider=event.provider, trade_id=event.trade_id, amount_cents=990)
    with Session() as db:
        assert complete_refund(db, proof).status == "succeeded"
        assert complete_refund(db, proof).status == "succeeded"
        assert refund_unknown(db, rid, uid).status == "succeeded"
    assert pay(event.model_copy(update={"event_id": str(uuid4())}))["status"] == "refunded"
    with Session() as db:
        entitlement = db.scalar(select(Entitlement).where(Entitlement.order_id == oid))
        assert entitlement.status == "refunded"


def test_foreign_refund_and_mismatched_proof_cannot_change_state(orders):
    oid, uid = orders[0]
    event = receipt(oid)
    pay(event)
    with Session() as db:
        with pytest.raises(HTTPException) as error:
            begin_refund(db, oid, orders[1][1])
        assert error.value.status_code == 404
        db.rollback()
        rid = begin_refund(db, oid, uid).id
    with Session() as db:
        with pytest.raises(HTTPException):
            complete_refund(db, VerifiedRefund(refund_id=rid, order_id=oid, provider=event.provider, trade_id=event.trade_id, amount_cents=1))
    with Session() as db:
        assert db.get(Order, oid).status == "refund_pending"
        assert db.get(Refund, rid).status == "pending"


@pytest.mark.parametrize("status", ["reserved", "consumed"])
def test_automatic_refund_does_not_race_generation(orders, status):
    oid, uid = orders[0]
    pay(receipt(oid))
    with Session.begin() as db:
        db.scalar(select(Entitlement).where(Entitlement.order_id == oid)).status = status
    with Session() as db:
        with pytest.raises(HTTPException) as error:
            begin_refund(db, oid, uid)
        assert error.value.status_code == 409
    with Session() as db:
        assert db.get(Order, oid).status == "paid"
        assert not db.scalar(select(Refund).where(Refund.order_id == oid))


def test_closed_order_cannot_be_reopened_by_late_paid_receipt(orders):
    event = receipt(orders[0][0], status="closed")
    pay(event)
    assert pay(event.model_copy(update={"event_id": str(uuid4()), "status": "paid"}))["status"] == "closed"
    with Session() as db:
        assert not db.scalar(select(Entitlement).where(Entitlement.order_id == event.order_id))


def test_closed_after_payment_freezes_delivery_for_reconciliation(orders):
    event = receipt(orders[0][0])
    pay(event)
    assert pay(event.model_copy(update={"event_id": str(uuid4()), "status": "closed"}))["status"] == "payment_review"
    assert pay(event.model_copy(update={"event_id": str(uuid4())}))["status"] == "payment_review"
    with Session() as db:
        assert db.scalar(select(Entitlement).where(Entitlement.order_id == event.order_id)).status == "held"


def test_concurrent_refund_submit_claim_has_one_winner(orders):
    oid, uid = orders[0]
    pay(receipt(oid))
    with Session() as db:
        rid = begin_refund(db, oid, uid).id
    def claim(_):
        with Session() as db:
            return claim_refund(db, rid, uid)
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(claim, range(2))) == [False, True]
