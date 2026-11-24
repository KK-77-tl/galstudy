import asyncio
import hmac
import json
import os
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, Request, Header
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import defer
from .db import (
    Session,
    User,
    Product,
    Order,
    Entitlement,
    ReferenceImage,
    ImageJob,
    ImageAsset,
    CharacterRecord,
    ChatSession,
    ChatMessage,
)
from . import workshop, images, payments
from .characters import CHARACTERS


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str = workshop.SKU
    request_id: str = Field(min_length=36, max_length=36)


class SimulatePayment(BaseModel):
    status: Literal["paid", "failed"]


class JobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=36, max_length=36)
    entitlement_id: str
    reference_id: str
    name: str = Field(min_length=1, max_length=40)
    persona: str = Field(min_length=1, max_length=1000)
    address: str = Field(min_length=1, max_length=40)
    appearance: str = Field(max_length=400, default="")
    demo_template: Literal["shiori", "haruka", "rin"] = "shiori"


class ReviewInput(BaseModel):
    approved: bool


class SelectionInput(BaseModel):
    character_id: str | None = None


def database():
    with Session() as db:
        yield db


def job_view(job):
    spec = json.loads(job.spec)
    return {
        "id": job.id,
        "status": job.status,
        "mode": job.mode,
        "attempts": job.attempts,
        "max_attempts": workshop.MAX_ATTEMPTS,
        "error": job.error,
        "name": spec.get("name", "已删除角色"),
        "created_at": job.created_at,
        "entitlement_id": job.entitlement_id,
    }


def character_view(character):
    return {
        "id": character.id,
        "name": character.name,
        "persona": character.persona,
        "mode": character.mode,
        "assets": [
            {**asset, "url": "/api/workshop/assets/" + asset["asset_id"]}
            for asset in json.loads(character.assets)
        ],
    }


def operator(token):
    expected = os.getenv("WORKSHOP_REVIEW_TOKEN", "")
    if (
        not expected
        or not token
        or not hmac.compare_digest(token.encode(), expected.encode())
    ):
        raise HTTPException(403, "需要服务端审核人员权限")


def build_router(user_dependency):
    router = APIRouter(prefix="/api/workshop", tags=["角色工坊"])

    @router.get("/products")
    def products(current: User = Depends(user_dependency), db=Depends(database)):
        return [
            {
                "id": p.id,
                "title": p.title if payments.payment_provider.mode == "mock" else "专属角色静态包",
                "price_cents": p.price_cents,
                "currency": p.currency,
                "pack": json.loads(p.pack_spec),
                "payment_mode": payments.payment_provider.mode,
                "image_mode": images.image_generator.mode,
                "reference_retention_days": workshop.REFERENCE_RETENTION_DAYS,
            }
            for p in db.scalars(select(Product))
        ]

    @router.post("/orders")
    def create_order(
        payload: OrderInput,
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        workshop.lock_user(db, current.id)
        previous = db.scalar(
            select(Order).where(
                Order.user_id == current.id, Order.request_id == payload.request_id
            )
        )
        if previous:
            if previous.product_id != payload.product_id:
                raise HTTPException(409, "请求编号已用于其他商品")
            db.commit()
            return workshop.order_view(db, previous)
        product = db.get(Product, payload.product_id)
        if not product:
            raise HTTPException(404, "商品不存在")
        order = Order(
            id=workshop.uid(),
            user_id=current.id,
            request_id=payload.request_id,
            product_id=product.id,
            amount_cents=product.price_cents,
            pack_spec=product.pack_spec,
            currency=product.currency,
            provider=payments.payment_provider.mode,
            status="pending",
            created_at=int(time.time()),
        )
        db.add(order)
        db.commit()
        return workshop.order_view(db, order)

    @router.get("/orders")
    def orders(current: User = Depends(user_dependency), db=Depends(database)):
        return [
            workshop.order_view(db, order)
            for order in db.scalars(
                select(Order)
                .where(Order.user_id == current.id)
                .order_by(Order.created_at.desc())
            )
        ]

    @router.get("/orders/{order_id}")
    def get_order(
        order_id: str, current: User = Depends(user_dependency), db=Depends(database)
    ):
        return workshop.order_view(db, workshop.owned(db, Order, order_id, current.id))

    @router.post("/orders/{order_id}/simulate")
    def simulate(
        order_id: str,
        payload: SimulatePayment,
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        order = workshop.owned(db, Order, order_id, current.id)
        if order.provider != "mock":
            raise HTTPException(409, "仅模拟订单支持此操作")
        body = payments.notification_body(
            order,
            payload.status,
            workshop.uid(),
            order.provider_trade_id or "mock-" + order.id,
        )
        workshop.accept_notification(db, body, payments.mock_payment_provider.sign(body))
        return workshop.order_view(db, db.get(Order, order_id))

    @router.post("/payments/mock/notify")
    async def notify(
        request: Request,
        x_mock_signature: str = Header(default=""),
        db=Depends(database),
    ):
        body = await request.body()
        if len(body) > 4096:
            raise HTTPException(413, "通知内容过大")
        return workshop.accept_notification(db, body, x_mock_signature)

    @router.post("/references", status_code=201)
    async def upload_reference(
        file: UploadFile,
        rights_confirmed: bool = Form(...),
        contains_real_person: bool = Form(False),
        person_consent_confirmed: bool = Form(False),
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        if not rights_confirmed or (
            contains_real_person and not person_consent_confirmed
        ):
            raise HTTPException(422, "请确认素材使用权及真人照片的适当同意")
        data = await file.read(5 * 1024 * 1024 + 1)
        await file.close()
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, "参考图最大5MB")
        try:
            normalized = await asyncio.to_thread(images.normalized_image, data)
        except images.GenerationError as error:
            raise HTTPException(422, str(error))
        workshop.lock_user(db, current.id)
        count = db.scalar(
            select(func.count())
            .select_from(ReferenceImage)
            .where(ReferenceImage.user_id == current.id)
        )
        if count >= 10:
            raise HTTPException(429, "最多保存10张参考图，请先删除不再使用的图片")
        now = int(time.time())
        reference = ReferenceImage(
            id=workshop.uid(),
            user_id=current.id,
            data=normalized,
            status="pending_review",
            contains_real_person=contains_real_person,
            rights_confirmed=True,
            person_consent_confirmed=person_consent_confirmed,
            created_at=now,
            expires_at=now + workshop.REFERENCE_RETENTION_DAYS * 86400,
        )
        db.add(reference)
        db.commit()
        return {
            "id": reference.id,
            "status": reference.status,
            "expires_at": reference.expires_at,
        }

    @router.get("/references")
    def references(current: User = Depends(user_dependency), db=Depends(database)):
        return [
            {
                "id": r.id,
                "status": r.status,
                "expires_at": r.expires_at,
                "url": "/api/workshop/references/" + r.id,
            }
            for r in db.scalars(
                select(ReferenceImage)
                .options(defer(ReferenceImage.data))
                .where(ReferenceImage.user_id == current.id)
            )
        ]

    @router.get("/references/{reference_id}")
    def reference_image(
        reference_id: str,
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        reference = workshop.owned(db, ReferenceImage, reference_id, current.id)
        if reference.expires_at <= time.time():
            raise HTTPException(404, "参考图已到保留期")
        return Response(
            reference.data,
            media_type="image/png",
            headers={"Cache-Control": "private, no-store"},
        )

    @router.post("/references/{reference_id}/review")
    def review_reference(
        reference_id: str,
        payload: ReviewInput,
        x_workshop_review_token: str = Header(default=""),
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        workshop.lock_user(db, current.id)
        reference = workshop.owned(db, ReferenceImage, reference_id, current.id)
        if images.image_generator.mode != "mock":
            raise HTTPException(409, "真实参考图由后台审核人员处理")
        reference.status = "approved" if payload.approved else "rejected"
        db.commit()
        return {
            "status": reference.status,
            "review_mode": (
                "simulated" if images.image_generator.mode == "mock" else "operator"
            ),
        }

    @router.delete("/references/{reference_id}")
    async def delete_reference(
        reference_id: str,
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        workshop.lock_user(db, current.id)
        reference = workshop.owned(db, ReferenceImage, reference_id, current.id)
        remote = []
        for job in db.scalars(
            select(ImageJob).where(ImageJob.reference_id == reference_id)
        ):
            if job.status not in {"complete", "failed", "cancelled"} and job.remote_id:
                remote.append(job.remote_id)
            workshop.fail_job(
                db,
                job,
                "参考图已删除，未完成任务已取消，权益已恢复。",
                status="cancelled",
            )
            job.reference_id = None
        db.delete(reference)
        db.commit()
        for remote_id in remote:
            await images.image_generator.cancel(remote_id)
        return {"ok": True}

    @router.post("/jobs", status_code=202)
    def create_job(
        payload: JobInput,
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        values = payload.model_dump()
        spec = {
            key: values[key]
            for key in ("name", "persona", "address", "appearance", "demo_template")
        }
        if any(not spec[key].strip() for key in ("name", "persona", "address")):
            raise HTTPException(422, "角色名字、人设与称呼不能为空")
        return job_view(
            workshop.reserve_job(
                db,
                current.id,
                payload.entitlement_id,
                payload.reference_id,
                payload.request_id,
                spec,
            )
        )

    @router.get("/jobs")
    def jobs(current: User = Depends(user_dependency), db=Depends(database)):
        return [
            job_view(job)
            for job in db.scalars(
                select(ImageJob)
                .where(ImageJob.user_id == current.id)
                .order_by(ImageJob.created_at.desc())
            )
        ]

    @router.post("/jobs/{job_id}/retry")
    def retry(
        job_id: str, current: User = Depends(user_dependency), db=Depends(database)
    ):
        workshop.lock_user(db, current.id)
        job = workshop.owned(db, ImageJob, job_id, current.id)
        reference = (
            db.get(ReferenceImage, job.reference_id) if job.reference_id else None
        )
        entitlement = db.get(Entitlement, job.entitlement_id)
        order = db.get(Order, entitlement.order_id)
        if (
            job.status != "failed"
            or job.attempts >= workshop.MAX_ATTEMPTS
            or not reference
            or reference.status != "approved"
            or reference.expires_at <= time.time()
            or entitlement.status != "available"
            or order.status != "paid"
            or (images.image_generator.mode != "mock" and order.provider != "alipay_live")
        ):
            raise HTTPException(409, "当前任务无法重试，请检查参考图、权益和重试次数")
        entitlement.status = "reserved"
        entitlement.reservation_job_id = job.id
        job.status = "queued"
        job.remote_id = None
        job.error = ""
        job.updated_at = int(time.time())
        db.commit()
        return job_view(job)

    @router.post("/operator/jobs/{job_id}/review")
    def review_job(
        job_id: str,
        payload: ReviewInput,
        x_workshop_review_token: str = Header(default=""),
        db=Depends(database),
    ):
        operator(x_workshop_review_token)
        job = db.get(ImageJob, job_id)
        if not job:
            raise HTTPException(404, "任务不存在")
        workshop.lock_user(db, job.user_id)
        db.refresh(job)
        if job.status != "reviewing":
            raise HTTPException(409, "任务不处于待审核状态")
        if payload.approved:
            workshop.deliver(db, job)
        else:
            workshop.fail_job(db, job, "输出审核未通过，权益已恢复。")
        db.commit()
        return job_view(job)

    @router.get("/characters")
    def character_library(
        current: User = Depends(user_dependency), db=Depends(database)
    ):
        return [
            character_view(c)
            for c in db.scalars(
                select(CharacterRecord).where(CharacterRecord.user_id == current.id)
            )
        ]

    @router.get("/assets/{asset_id}")
    def asset(
        asset_id: str, current: User = Depends(user_dependency), db=Depends(database)
    ):
        asset = workshop.owned(db, ImageAsset, asset_id, current.id)
        if db.get(ImageJob, asset.job_id).status != "complete":
            raise HTTPException(404, "资产尚未交付")
        return Response(
            asset.data,
            media_type="image/png",
            headers={"Cache-Control": "private, no-store"},
        )

    @router.put("/selection")
    def select_character(
        payload: SelectionInput,
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        account = workshop.lock_user(db, current.id)
        if payload.character_id and payload.character_id not in CHARACTERS:
            workshop.owned(db, CharacterRecord, payload.character_id, current.id)
        account.selected_character_id = payload.character_id
        db.commit()
        return {"selected_character_id": payload.character_id}

    @router.delete("/characters/{character_id}")
    def delete_character(
        character_id: str,
        current: User = Depends(user_dependency),
        db=Depends(database),
    ):
        account = workshop.lock_user(db, current.id)
        character = workshop.owned(db, CharacterRecord, character_id, current.id)
        sessions = select(ChatSession.id).where(
            ChatSession.user_id == current.id, ChatSession.character_id == character_id
        )
        db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(sessions)))
        db.execute(
            delete(ChatSession).where(
                ChatSession.user_id == current.id,
                ChatSession.character_id == character_id,
            )
        )
        db.execute(delete(ImageAsset).where(ImageAsset.job_id == character.job_id))
        job = db.get(ImageJob, character.job_id)
        job.spec = json.dumps({"deleted": True})
        if account.selected_character_id == character_id:
            account.selected_character_id = None
        db.delete(character)
        db.commit()
        return {"ok": True}

    @router.post("/operator/references/{reference_id}/review")
    def operator_reference(
        reference_id: str,
        payload: ReviewInput,
        x_workshop_review_token: str = Header(default=""),
        db=Depends(database),
    ):
        operator(x_workshop_review_token)
        reference = db.get(ReferenceImage, reference_id)
        if not reference or reference.expires_at <= time.time():
            raise HTTPException(404, "参考图不存在或已过期")
        workshop.lock_user(db, reference.user_id)
        reference = db.get(ReferenceImage, reference_id, populate_existing=True)
        if not reference or reference.expires_at <= time.time():
            raise HTTPException(404, "参考图不存在或已过期")
        reference.status = "approved" if payload.approved else "rejected"
        db.commit()
        return {"status": reference.status, "review_mode": "operator"}

    @router.get("/operator/references/{reference_id}")
    def operator_reference_image(
        reference_id: str,
        x_workshop_review_token: str = Header(default=""),
        db=Depends(database),
    ):
        operator(x_workshop_review_token)
        reference = db.get(ReferenceImage, reference_id)
        if not reference or reference.expires_at <= time.time():
            raise HTTPException(404)
        return Response(
            reference.data,
            media_type="image/png",
            headers={"Cache-Control": "private, no-store"},
        )

    @router.get("/operator/queue")
    def operator_queue(
        x_workshop_review_token: str = Header(default=""), db=Depends(database)
    ):
        operator(x_workshop_review_token)
        return {
            "references": [
                {
                    "id": ref.id,
                    "contains_real_person": ref.contains_real_person,
                    "person_consent_confirmed": ref.person_consent_confirmed,
                }
                for ref in db.scalars(
                    select(ReferenceImage)
                    .options(defer(ReferenceImage.data))
                    .where(
                        ReferenceImage.status == "pending_review",
                        ReferenceImage.expires_at > time.time(),
                    )
                )
            ],
            "jobs": [
                {
                    "id": job.id,
                    "asset_ids": list(
                        db.scalars(
                            select(ImageAsset.id).where(ImageAsset.job_id == job.id)
                        )
                    ),
                }
                for job in db.scalars(
                    select(ImageJob).where(ImageJob.status == "reviewing")
                )
            ],
        }

    @router.get("/operator/assets/{asset_id}")
    def operator_asset(
        asset_id: str,
        x_workshop_review_token: str = Header(default=""),
        db=Depends(database),
    ):
        operator(x_workshop_review_token)
        asset = db.get(ImageAsset, asset_id)
        if not asset:
            raise HTTPException(404)
        return Response(
            asset.data,
            media_type="image/png",
            headers={"Cache-Control": "private, no-store"},
        )

    from .alipay_api import build_alipay_router
    router.include_router(build_alipay_router(user_dependency))
    return router
