"""Transactional order, entitlement, reference and image-job lifecycle."""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update, delete, func, text, and_, or_
from sqlalchemy.orm import defer
from .db import (
    Session,
    engine,
    User,
    Product,
    Order,
    PaymentEvent,
    Entitlement,
    ReferenceImage,
    ImageJob,
    ImageSubmissionUsage,
    ImageAsset,
    CharacterRecord,
    Refund,
    ChatSession,
    ChatMessage,
)
from . import images, payments
from .characters import CHARACTERS

SKU = "character-static-demo"
MAX_ATTEMPTS = 3
REFERENCE_RETENTION_DAYS = int(os.getenv("REFERENCE_RETENTION_DAYS", "7"))
JOB_TIMEOUT_SECONDS = int(os.getenv("IMAGE_JOB_TIMEOUT_SECONDS", "300"))
USER_DAILY_JOBS = int(os.getenv("IMAGE_USER_DAILY_LIMIT", "5"))
GLOBAL_DAILY_JOBS = int(os.getenv("IMAGE_GLOBAL_DAILY_LIMIT", "20"))
USER_DAILY_SUBMISSIONS = int(os.getenv("IMAGE_USER_DAILY_SUBMISSION_LIMIT", "15"))
GLOBAL_DAILY_SUBMISSIONS = int(os.getenv("IMAGE_GLOBAL_DAILY_SUBMISSION_LIMIT", "60"))


def uid():
    return str(uuid4())


def lock_user(db, user_id):
    if engine.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    account = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not account:
        raise HTTPException(404, "账号不存在")
    return account


def seed_product():
    config = {
        "expressions": int(os.getenv("CHARACTER_EXPRESSION_COUNT", "6")),
        "poses": int(os.getenv("CHARACTER_POSE_COUNT", "3")),
    }
    price = int(os.getenv("CHARACTER_PACK_PRICE_CENTS", "990"))
    if (
        not 1 <= price <= 1000000
        or not 0 <= config["expressions"] <= 12
        or not 0 <= config["poses"] <= 6
        or not 1 <= REFERENCE_RETENTION_DAYS <= 30
    ):
        raise RuntimeError("角色商品或保留期配置超出支持范围")
    with Session.begin() as db:
        product = db.get(Product, SKU)
        if not product:
            product = Product(
                id=SKU,
                title="专属角色静态包 · Mock",
                price_cents=price,
                currency="CNY",
                pack_spec=json.dumps(config),
            )
            db.add(product)
        else:
            product.price_cents = price
            product.pack_spec = json.dumps(config)


def owned(db, model, record_id, user_id):
    record = db.scalar(
        select(model).where(model.id == record_id, model.user_id == user_id)
    )
    if not record:
        raise HTTPException(404, "记录不存在")
    return record


def order_view(db, order):
    entitlement = db.scalar(select(Entitlement).where(Entitlement.order_id == order.id))
    refund = db.scalar(select(Refund).where(Refund.order_id == order.id))
    return {
        "checkout": payments.checkout_for(order),
        "id": order.id,
        "amount_cents": order.amount_cents,
        "currency": order.currency,
        "status": order.status,
        "mode": order.provider,
        "created_at": order.created_at,
        "pack": json.loads(order.pack_spec),
        "refund": ({"id": refund.id, "status": refund.status, "updated_at": refund.updated_at} if refund else None),
        "entitlement": (
            {"id": entitlement.id, "status": entitlement.status}
            if entitlement
            else None
        ),
    }


def accept_notification(db, body, signature):
    if not payments.mock_payment_provider.verify(body, signature):
        raise HTTPException(400, "模拟支付通知验签失败")
    try:
        event = payments.PaymentNotice.model_validate_json(body).model_dump()
    except ValidationError:
        raise HTTPException(400, "支付通知格式无效")
    order = db.get(Order, event["order_id"])
    if not order:
        raise HTTPException(404, "订单不存在")
    lock_user(db, order.user_id)
    db.refresh(order)
    digest = hashlib.sha256(body).hexdigest()
    previous = db.get(PaymentEvent, event["event_id"])
    if previous:
        if previous.digest != digest:
            raise HTTPException(409, "通知编号已被其他内容使用")
        db.commit()
        return {"ok": True, "duplicate": True, "mode": "mock"}
    if (
        type(event["amount_cents"]) is not int
        or event["amount_cents"] != order.amount_cents
        or event["currency"] != order.currency
        or order.provider != "mock"
    ):
        raise HTTPException(400, "通知金额、币种或订单不匹配")
    if event["status"] == "paid":
        if order.provider_trade_id and order.provider_trade_id != event["trade_id"]:
            raise HTTPException(409, "交易编号与订单不匹配")
        order.status = "paid"
        order.provider_trade_id = event["trade_id"]
        if not db.scalar(
            select(Entitlement.id).where(Entitlement.order_id == order.id)
        ):
            db.add(
                Entitlement(
                    id=uid(),
                    order_id=order.id,
                    user_id=order.user_id,
                    status="available",
                )
            )
    elif order.status != "paid":
        order.status = "failed"
    db.add(
        PaymentEvent(
            id=event["event_id"],
            order_id=order.id,
            digest=digest,
            status=event["status"],
            created_at=int(time.time()),
        )
    )
    db.commit()
    return {"ok": True, "duplicate": False, "mode": "mock"}


def fail_job(db, job, error, status="failed"):
    if job.status in {"complete", "cancelled", "failed"}:
        return
    job.status = status
    job.error = error
    job.updated_at = int(time.time())
    db.execute(
        update(Entitlement)
        .where(
            Entitlement.id == job.entitlement_id,
            Entitlement.status == "reserved",
            Entitlement.reservation_job_id == job.id,
        )
        .values(status="available", reservation_job_id=None)
    )
    db.execute(delete(ImageAsset).where(ImageAsset.job_id == job.id))


def reserve_job(db, user_id, entitlement_id, reference_id, request_id, spec):
    lock_user(db, user_id)
    existing = db.scalar(
        select(ImageJob).where(
            ImageJob.user_id == user_id, ImageJob.request_id == request_id
        )
    )
    if existing:
        if (
            any(
                json.loads(existing.spec).get(key) != value
                for key, value in spec.items()
            )
            or existing.reference_id != reference_id
            or existing.entitlement_id != entitlement_id
        ):
            raise HTTPException(409, "请求编号已用于其他生成内容")
        db.commit()
        return existing
    reference = owned(db, ReferenceImage, reference_id, user_id)
    if reference.status != "approved" or reference.expires_at <= time.time():
        raise HTTPException(409, "参考图需先审核通过且未过保留期")
    entitlement = owned(db, Entitlement, entitlement_id, user_id)
    order = db.get(Order, entitlement.order_id)
    if images.image_generator.mode != "mock" and order.provider != "alipay_live":
        raise HTTPException(409, "演示或沙箱付款权益不能用于真实GPU生成。")
    if order.status != "paid" or entitlement.status != "available":
        raise HTTPException(409, "付款成功并有可用权益后才能生成")
    day = (
        datetime.now(timezone(timedelta(hours=8)))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    if engine.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(428901)"))
    total = db.scalar(
        select(func.count()).select_from(ImageJob).where(ImageJob.created_at >= day)
    )
    personal = db.scalar(
        select(func.count())
        .select_from(ImageJob)
        .where(ImageJob.created_at >= day, ImageJob.user_id == user_id)
    )
    if total >= GLOBAL_DAILY_JOBS or personal >= USER_DAILY_JOBS:
        raise HTTPException(429, "今日角色任务额度已用完，请明天再来")
    spec = {**spec, **json.loads(order.pack_spec)}
    job = ImageJob(
        id=uid(),
        user_id=user_id,
        request_id=request_id,
        entitlement_id=entitlement_id,
        reference_id=reference_id,
        spec=json.dumps(spec, sort_keys=True, ensure_ascii=False),
        mode=images.image_generator.mode,
        status="queued",
        attempts=0,
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )
    db.add(job)
    entitlement.status = "reserved"
    entitlement.reservation_job_id = job.id
    db.commit()
    return job


def generation_authorized(db, job):
    entitlement = db.get(Entitlement, job.entitlement_id)
    order = db.get(Order, entitlement.order_id) if entitlement else None
    return bool(order and order.status == "paid" and entitlement.status == "reserved"
                and entitlement.reservation_job_id == job.id
                and (job.mode == "mock" or order.provider == "alipay_live"))


def deliver(db, job):
    if not generation_authorized(db, job):
        raise HTTPException(409, "付款或生成权益状态已变化")
    entitlement = db.get(Entitlement, job.entitlement_id)
    if entitlement.status != "reserved" or entitlement.reservation_job_id != job.id:
        raise HTTPException(409, "生成权益状态不匹配")
    assets = db.scalars(
        select(ImageAsset)
        .options(defer(ImageAsset.data))
        .where(ImageAsset.job_id == job.id)
        .order_by(ImageAsset.slot)
    ).all()
    spec = json.loads(job.spec)
    labels = (
        [("portrait", "主立绘")]
        + [("expression", f"表情 {index+1}") for index in range(spec["expressions"])]
        + [("pose", f"姿态 {index+1}") for index in range(spec["poses"])]
    )
    if not assets or (job.mode != "mock" and len(assets) != len(labels)):
        raise HTTPException(409, "角色包资产数量不完整")
    manifest = [
        {
            "kind": kind,
            "label": label,
            "asset_id": assets[0 if job.mode == "mock" else index].id,
            "placeholder": job.mode == "mock" and index > 0,
        }
        for index, (kind, label) in enumerate(labels)
    ]
    character = CharacterRecord(
        id=uid(),
        user_id=job.user_id,
        job_id=job.id,
        entitlement_id=job.entitlement_id,
        name=spec["name"],
        persona=spec["persona"],
        address=spec["address"],
        mode=job.mode,
        assets=json.dumps(manifest, ensure_ascii=False),
    )
    db.add(character)
    entitlement.status = "consumed"
    entitlement.reservation_job_id = None
    job.status = "complete"
    job.updated_at = int(time.time())


async def process_job(job_id):
    with Session() as db:
        job = db.get(ImageJob, job_id)
        if not job or job.status not in {"queued", "generating", "reviewing"}:
            return
        user_id = job.user_id
    try:
        with Session.begin() as db:
            lock_user(db, user_id)
            job = db.get(ImageJob, job_id)
            if job.status not in {"queued", "generating", "reviewing"}:
                return
            if not generation_authorized(db, job):
                fail_job(db, job, "付款或生成权益状态已变化，任务已停止。")
                return
            reference = (
                db.get(
                    ReferenceImage,
                    job.reference_id,
                    options=[defer(ReferenceImage.data)],
                )
                if job.reference_id
                else None
            )
            if (
                not reference
                or reference.status != "approved"
                or reference.expires_at <= time.time()
            ):
                fail_job(db, job, "参考图已删除、过期或未通过审核。")
                return
            if (
                job.status == "generating"
                and time.time() - job.updated_at > JOB_TIMEOUT_SECONDS
            ):
                fail_job(db, job, "任务超时，生成权益已恢复。")
                return
            if job.status == "reviewing":
                if job.mode == "mock":
                    deliver(db, job)
                return
            status = job.status
            spec = json.loads(job.spec)
            data = reference.data if status == "queued" else b""
            remote_id = job.remote_id
            if status == "queued":
                if not reserve_submission(db, user_id):
                    fail_job(
                        db, job, "今日生成提交额度已用完，权益已恢复，请明天重试。"
                    )
                    return
                job.attempts += 1
                job.status = "submitting"
                job.updated_at = int(time.time())
        provider = images.image_generator
        if provider.mode != job.mode:
            raise images.GenerationError("生成服务模式已变化，请重试。")
        if status == "queued":
            remote_id = await asyncio.wait_for(provider.submit(spec, data), 30)
            cancel = False
            with Session.begin() as db:
                lock_user(db, user_id)
                current = db.get(ImageJob, job_id)
                if current.status == "submitting":
                    current.remote_id = remote_id
                    current.status = "generating"
                    current.updated_at = int(time.time())
                else:
                    cancel = True
            if cancel:
                await provider.cancel(remote_id)
        else:
            results = await asyncio.wait_for(provider.poll(remote_id, spec), 30)
            if results is None:
                return
            with Session.begin() as db:
                lock_user(db, user_id)
                current = db.get(ImageJob, job_id)
                if current.status != "generating":
                    return
                if not generation_authorized(db, current):
                    fail_job(db, current, "付款或生成权益状态已变化，任务已停止。")
                    return
                for slot, data in enumerate(results):
                    db.add(
                        ImageAsset(
                            id=uid(),
                            user_id=user_id,
                            job_id=job_id,
                            data=data,
                            slot=slot,
                        )
                    )
                current.status = "reviewing"
                current.updated_at = int(time.time())
    except Exception as error:
        with Session.begin() as db:
            lock_user(db, user_id)
            job = db.get(ImageJob, job_id)
            message = (
                str(error)
                if isinstance(error, images.GenerationError)
                else "生成任务失败，权益已恢复，请重试。"
            )
            fail_job(db, job, message)


def reserve_submission(db, user_id):
    """Reserve every provider submit, including retries of jobs from earlier days.

    The caller holds the user write lock. Failed/ambiguous submissions retain usage.
    """
    if engine.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(428901)"))
    day = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    buckets = [
        (f"{day}:global", GLOBAL_DAILY_SUBMISSIONS),
        (f"{day}:{user_id}", USER_DAILY_SUBMISSIONS),
    ]
    records = []
    for bucket, limit in buckets:
        record = db.get(ImageSubmissionUsage, bucket)
        if record and record.submissions >= limit:
            return False
        if limit <= 0:
            return False
        if not record:
            record = ImageSubmissionUsage(bucket=bucket, submissions=0)
            db.add(record)
        records.append(record)
    for record in records:
        record.submissions += 1
    return True


async def worker():
    while True:
        with Session() as db:
            pending = list(
                db.scalars(
                    select(ImageJob.id)
                    .where(
                        or_(
                            ImageJob.status.in_(["queued", "generating"]),
                            and_(
                                ImageJob.status == "reviewing", ImageJob.mode == "mock"
                            ),
                        )
                    )
                    .order_by(ImageJob.updated_at)
                    .limit(10)
                )
            )
        for job_id in pending:
            await process_job(job_id)
        with Session() as db:
            expired = list(
                db.scalars(
                    select(ReferenceImage.id).where(
                        ReferenceImage.expires_at <= time.time()
                    )
                )
            )
        for reference_id in expired:
            with Session.begin() as db:
                reference = db.get(ReferenceImage, reference_id)
                if not reference:
                    continue
                lock_user(db, reference.user_id)
                for job in db.scalars(
                    select(ImageJob).where(ImageJob.reference_id == reference.id)
                ):
                    fail_job(
                        db, job, "参考图已到保留期，权益已恢复。", status="cancelled"
                    )
                    job.reference_id = None
                db.delete(reference)
        await asyncio.sleep(0.6)
