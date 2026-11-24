import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import pytest
import httpx
from PIL import Image, PngImagePlugin
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from backend.main import app
from backend.db import (
    Session,
    Order,
    Entitlement,
    ImageJob,
    ImageAsset,
    CharacterRecord,
    PaymentEvent,
    ImageSubmissionUsage,
)
from backend import workshop, images, payments


class ImmediateMock(images.MockCharacterGenerator):
    async def poll(self, remote_id, spec):
        return await super().poll("mock-0", spec)


@pytest.fixture
def clients(monkeypatch):
    async def idle():
        await asyncio.Event().wait()

    monkeypatch.setattr(workshop, "worker", idle)
    monkeypatch.setattr(images, "image_generator", ImmediateMock())
    with TestClient(app) as a, TestClient(app) as b:
        for client in [a, b]:
            client.post(
                "/api/auth/register",
                json={
                    "email": uuid4().hex + "@example.com",
                    "password": "workshop-test-pass",
                },
            )
        yield a, b


def picture():
    output = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "remove metadata")
    Image.new("RGB", (256, 256), "#aabb99").save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


def test_mock_entitlement_cannot_purchase_real_gpu_time(clients, monkeypatch):
    from types import SimpleNamespace
    a, _ = clients
    rid = reference(a)
    paid = order(a)
    monkeypatch.setattr(images, "image_generator", SimpleNamespace(mode="comfyui"))
    response = a.post("/api/workshop/jobs", json=job_payload(paid["entitlement"]["id"], rid))
    assert response.status_code == 409 and "真实GPU" in response.json()["detail"]


def reference(client):
    response = client.post(
        "/api/workshop/references",
        data={"rights_confirmed": "true"},
        files={"file": ("original.png", picture(), "image/png")},
    )
    assert response.status_code == 201
    rid = response.json()["id"]
    assert (
        client.post(
            f"/api/workshop/references/{rid}/review", json={"approved": True}
        ).json()["review_mode"]
        == "simulated"
    )
    return rid


def order(client, paid=True):
    response = client.post("/api/workshop/orders", json={"request_id": str(uuid4())})
    assert response.status_code == 200
    result = response.json()
    if paid:
        result = client.post(
            f'/api/workshop/orders/{result["id"]}/simulate', json={"status": "paid"}
        ).json()
    return result


def job_payload(entitlement_id, reference_id):
    return {
        "request_id": str(uuid4()),
        "entitlement_id": entitlement_id,
        "reference_id": reference_id,
        "name": "青禾",
        "persona": "耐心、有条理，喜欢用提问帮助回忆。",
        "address": "小伙伴",
        "appearance": "校园开衫",
        "demo_template": "shiori",
    }


def test_daily_submission_budget_covers_old_job_retries(clients, monkeypatch):
    a, _ = clients
    monkeypatch.setattr(workshop, "USER_DAILY_SUBMISSIONS", 1)
    monkeypatch.setattr(workshop, "GLOBAL_DAILY_SUBMISSIONS", 10000)
    rid = reference(a)
    entitlement_id = order(a)["entitlement"]["id"]
    payload = job_payload(entitlement_id, rid)
    job_id = a.post("/api/workshop/jobs", json=payload).json()["id"]
    with Session.begin() as db:
        job = db.get(ImageJob, job_id)
        user_id = job.user_id
        job.created_at = int(time.time()) - 86400 * 2

    class FailedSubmit(ImmediateMock):
        calls = 0

        async def submit(self, spec, data):
            self.calls += 1
            raise images.GenerationError("controlled submit failure")

    provider = FailedSubmit()
    monkeypatch.setattr(images, "image_generator", provider)
    asyncio.run(workshop.process_job(job_id))
    assert provider.calls == 1
    assert a.post(f"/api/workshop/jobs/{job_id}/retry").status_code == 200
    asyncio.run(workshop.process_job(job_id))
    assert provider.calls == 1
    with Session() as db:
        job = db.get(ImageJob, job_id)
        assert job.status == "failed"
        assert "今日生成提交额度" in job.error
        assert db.get(Entitlement, entitlement_id).status == "available"
        bucket = db.scalar(
            select(ImageSubmissionUsage).where(
                ImageSubmissionUsage.bucket.endswith(":" + user_id)
            )
        )
        assert bucket.submissions == 1


def notify(
    client, order_id, status="paid", event_id=None, amount=None, trade_id="mock-trade"
):
    with Session() as db:
        record = db.get(Order, order_id)
        body = payments.notification_body(
            record, status, event_id or str(uuid4()), trade_id
        )
    if amount is not None:
        value = json.loads(body)
        value["amount_cents"] = amount
        body = json.dumps(value).encode()
    return client.post(
        "/api/workshop/payments/mock/notify",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Mock-Signature": payments.payment_provider.sign(body),
        },
    )


def test_payment_price_signature_idempotency_and_ownership(clients):
    a, b = clients
    assert (
        a.post(
            "/api/workshop/orders", json={"request_id": str(uuid4()), "amount_cents": 1}
        ).status_code
        == 422
    )
    request_id = str(uuid4())
    created = a.post("/api/workshop/orders", json={"request_id": request_id}).json()
    assert (
        a.post("/api/workshop/orders", json={"request_id": request_id}).json()["id"]
        == created["id"]
    )
    oid = created["id"]
    assert (
        created["amount_cents"]
        == a.get("/api/workshop/products").json()[0]["price_cents"]
    )
    assert b.get("/api/workshop/orders/" + oid).status_code == 404
    assert (
        b.post(
            f"/api/workshop/orders/{oid}/simulate", json={"status": "paid"}
        ).status_code
        == 404
    )
    assert (
        a.post(
            "/api/workshop/payments/mock/notify",
            content=b"{}",
            headers={"X-Mock-Signature": "forged"},
        ).status_code
        == 400
    )
    assert notify(a, oid, amount=created["amount_cents"] + 1).status_code == 400
    failed = a.post(
        f"/api/workshop/orders/{oid}/simulate", json={"status": "failed"}
    ).json()
    assert failed["status"] == "failed" and failed["entitlement"] is None
    event_id = str(uuid4())
    assert notify(a, oid, event_id=event_id).status_code == 200
    replay = notify(a, oid, event_id=event_id)
    assert replay.json()["duplicate"]
    assert notify(a, oid, status="failed", event_id=event_id).status_code == 409
    assert notify(a, oid, status="failed").status_code == 200
    current = a.get("/api/workshop/orders/" + oid).json()
    assert (
        current["status"] == "paid" and current["entitlement"]["status"] == "available"
    )
    assert notify(a, oid, trade_id="different-trade").status_code == 409
    with Session() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Entitlement)
                .where(Entitlement.order_id == oid)
            )
            == 1
        )


def test_reference_validation_privacy_and_entitlement_reservation(clients):
    a, b = clients
    jpeg = BytesIO()
    metadata = Image.Exif()
    metadata[274] = 6
    metadata[315] = "private-owner"
    Image.new("RGB", (256, 128), "#998877").save(jpeg, format="JPEG", exif=metadata)
    clean = Image.open(BytesIO(images.normalized_image(jpeg.getvalue())))
    assert clean.size == (128, 256) and not clean.info and not clean.getexif()
    assert (
        a.post(
            "/api/workshop/references",
            data={"rights_confirmed": "false"},
            files={"file": ("x.png", picture())},
        ).status_code
        == 422
    )
    assert (
        a.post(
            "/api/workshop/references",
            data={"rights_confirmed": "true", "contains_real_person": "true"},
            files={"file": ("x.png", picture())},
        ).status_code
        == 422
    )
    assert (
        a.post(
            "/api/workshop/references",
            data={"rights_confirmed": "true"},
            files={"file": ("x.png", b"bad")},
        ).status_code
        == 422
    )
    rid = reference(a)
    private = a.get("/api/workshop/references/" + rid)
    assert private.status_code == 200 and "no-store" in private.headers["cache-control"]
    assert not Image.open(BytesIO(private.content)).info
    assert b.get("/api/workshop/references/" + rid).status_code == 404
    assert b.delete("/api/workshop/references/" + rid).status_code == 404
    assert (
        b.post(
            f"/api/workshop/references/{rid}/review", json={"approved": True}
        ).status_code
        == 404
    )
    unpaid = order(a, paid=False)
    assert unpaid["entitlement"] is None
    assert (
        a.post("/api/workshop/jobs", json=job_payload("missing", rid)).status_code
        == 404
    )
    paid = order(a)
    payload = job_payload(paid["entitlement"]["id"], rid)
    assert (
        a.post(
            "/api/workshop/jobs",
            json={**payload, "workflow": {}, "service_url": "http://127.0.0.1"},
        ).status_code
        == 422
    )
    assert b.post("/api/workshop/jobs", json=payload).status_code == 404
    inputs = [payload, {**payload, "request_id": str(uuid4())}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda data: a.post("/api/workshop/jobs", json=data), inputs)
        )
    assert sorted(result.status_code for result in results) == [202, 409]
    successful = next(result for result in results if result.status_code == 202).json()
    submitted = inputs[
        next(index for index, result in enumerate(results) if result.status_code == 202)
    ]
    assert a.post("/api/workshop/jobs", json=submitted).json()["id"] == successful["id"]
    assert (
        a.get("/api/workshop/orders/" + paid["id"]).json()["entitlement"]["status"]
        == "reserved"
    )


def test_generation_failure_retry_delivery_selection_and_deletion(clients, monkeypatch):
    a, b = clients
    rid = reference(a)
    paid = order(a)

    class Fail(images.MockCharacterGenerator):
        async def submit(self, *args):
            raise images.GenerationError("受控生成失败")

    monkeypatch.setattr(images, "image_generator", Fail())
    created = a.post(
        "/api/workshop/jobs", json=job_payload(paid["entitlement"]["id"], rid)
    ).json()
    jid = created["id"]
    assert (
        a.post(
            f"/api/workshop/operator/jobs/{jid}/review", json={"approved": True}
        ).status_code
        == 403
    )
    asyncio.run(workshop.process_job(jid))
    current = next(
        job for job in a.get("/api/workshop/jobs").json() if job["id"] == jid
    )
    assert current["status"] == "failed" and current["attempts"] == 1
    assert (
        a.get("/api/workshop/orders/" + paid["id"]).json()["entitlement"]["status"]
        == "available"
    )
    monkeypatch.setattr(images, "image_generator", ImmediateMock())
    assert b.post(f"/api/workshop/jobs/{jid}/retry").status_code == 404
    assert a.post(f"/api/workshop/jobs/{jid}/retry").status_code == 200
    asyncio.run(workshop.process_job(jid))
    asyncio.run(workshop.process_job(jid))
    with Session() as db:
        asset = db.scalar(select(ImageAsset).where(ImageAsset.job_id == jid))
        asset_id = asset.id
    assert a.get("/api/workshop/assets/" + asset_id).status_code == 404
    asyncio.run(workshop.process_job(jid))
    library = a.get("/api/workshop/characters").json()
    character = next(c for c in library if c["name"] == "青禾")
    assert (
        len(character["assets"]) == 10
        and sum(asset["placeholder"] for asset in character["assets"]) == 9
    )
    assert a.get("/api/workshop/assets/" + asset_id).status_code == 200
    assert b.get("/api/workshop/assets/" + asset_id).status_code == 404
    assert (
        b.put(
            "/api/workshop/selection", json={"character_id": character["id"]}
        ).status_code
        == 404
    )
    assert (
        a.put(
            "/api/workshop/selection", json={"character_id": character["id"]}
        ).status_code
        == 200
    )
    assert a.get("/api/auth/me").json()["selected_character_id"] == character["id"]
    assert any(c["id"] == character["id"] for c in a.get("/api/characters").json())
    assert all(c["id"] != character["id"] for c in b.get("/api/characters").json())
    cid = a.post("/api/courses", json={"title": "角色聊天"}).json()["id"]
    a.post(
        f"/api/courses/{cid}/points",
        json={"text": "检索练习是主动回忆。", "confirmed": True},
    )
    sid = a.post(
        f"/api/courses/{cid}/chat/sessions", json={"character_id": character["id"]}
    ).json()["id"]
    response = a.post(
        f"/api/chat/sessions/{sid}/messages",
        json={"request_id": str(uuid4()), "message": "检索练习"},
    )
    assert "青禾" in response.text and "小伙伴" in response.text
    assert a.delete("/api/workshop/references/" + rid).status_code == 200
    assert a.get("/api/workshop/assets/" + asset_id).status_code == 200
    assert a.delete("/api/workshop/characters/" + character["id"]).status_code == 200
    assert a.get("/api/workshop/assets/" + asset_id).status_code == 404
    assert a.get("/api/chat/sessions/" + sid).status_code == 404
    assert a.get("/api/auth/me").json()["selected_character_id"] is None
    assert (
        a.get("/api/workshop/orders/" + paid["id"]).json()["entitlement"]["status"]
        == "consumed"
    )


def test_generation_retry_limit_timeout_and_reference_cancellation(
    clients, monkeypatch
):
    a, _ = clients
    rid = reference(a)
    paid = order(a)

    class Fail(images.MockCharacterGenerator):
        async def submit(self, *args):
            raise images.GenerationError("受控错误")

    monkeypatch.setattr(images, "image_generator", Fail())
    jid = a.post(
        "/api/workshop/jobs", json=job_payload(paid["entitlement"]["id"], rid)
    ).json()["id"]
    for index in range(3):
        if index:
            assert a.post(f"/api/workshop/jobs/{jid}/retry").status_code == 200
        asyncio.run(workshop.process_job(jid))
    assert a.post(f"/api/workshop/jobs/{jid}/retry").status_code == 409
    monkeypatch.setattr(images, "image_generator", ImmediateMock())
    jid = a.post(
        "/api/workshop/jobs", json=job_payload(paid["entitlement"]["id"], rid)
    ).json()["id"]
    asyncio.run(workshop.process_job(jid))
    with Session.begin() as db:
        db.get(ImageJob, jid).updated_at = (
            int(time.time()) - workshop.JOB_TIMEOUT_SECONDS - 1
        )
    asyncio.run(workshop.process_job(jid))
    assert (
        a.get("/api/workshop/orders/" + paid["id"]).json()["entitlement"]["status"]
        == "available"
    )
    jid = a.post(
        "/api/workshop/jobs", json=job_payload(paid["entitlement"]["id"], rid)
    ).json()["id"]
    assert a.delete("/api/workshop/references/" + rid).status_code == 200
    current = next(
        job for job in a.get("/api/workshop/jobs").json() if job["id"] == jid
    )
    assert current["status"] == "cancelled"
    assert (
        a.get("/api/workshop/orders/" + paid["id"]).json()["entitlement"]["status"]
        == "available"
    )


def test_comfy_adapter_whitelist_and_private_output():
    path = Path(os.environ["GALSTUDY_TEST_ROOT"]) / "workflow.json"
    template = {
        "enabled": True,
        "prompt": {
            "1": {"class_type": "LoadImage", "inputs": {"image": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
            "4": {"class_type": "SaveImage", "inputs": {}},
        },
        "bindings": {
            "reference_image": {"node_id": "1", "input": "image"},
            "positive_prompt": {"node_id": "2", "input": "text"},
            "seed": {"node_id": "3", "input": "seed"},
        },
        "output_node_ids": ["4"],
    }
    path.write_text(json.dumps(template), encoding="utf-8")
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/upload/image"):
            return httpx.Response(200, json={"name": "private-reference.png"})
        if request.url.path.endswith("/prompt"):
            body = json.loads(request.content)
            assert body["prompt"]["1"]["inputs"]["image"] == "private-reference.png"
            assert body["prompt"]["3"]["inputs"]["seed"] >= 0
            return httpx.Response(200, json={"prompt_id": "private-job"})
        if "/history/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "private-job": {
                        "outputs": {
                            "4": {
                                "images": [{"filename": "result.png", "type": "output"}]
                            }
                        }
                    }
                },
            )
        if request.url.path.endswith("/view"):
            return httpx.Response(200, content=picture())
        return httpx.Response(200, json={})

    provider = images.ComfyUICharacterGenerator(
        "https://gpu.example.test", path, transport=httpx.MockTransport(handler)
    )
    spec = {"appearance": "campus", "persona": "kind", "expressions": 0, "poses": 0}

    async def run():
        remote = await provider.submit(spec, picture())
        result = await provider.poll(remote, spec)
        assert len(result) == 1 and not Image.open(BytesIO(result[0])).info
        await provider.cancel(remote)

    asyncio.run(run())
    assert seen == [
        "/upload/image",
        "/prompt",
        "/history/private-job",
        "/view",
        "/queue",
    ]
    with pytest.raises(images.GenerationError):
        images.ComfyUICharacterGenerator("file:///tmp/server", path)
