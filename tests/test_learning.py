import asyncio
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from backend import main, providers, chat
from backend.db import Session, Chunk, Course, LLMUsage
from backend.learning_provider import (
    OpenAICompatibleLLMProvider,
    validated_story,
    configured_learning_provider,
)
from scripts.make_samples import make_samples


def story_output(title, points):
    graph = providers.DemoLLMProvider().generate_story(title, points)
    nodes = {}
    for key, node in graph.nodes.items():
        item = node.model_dump(exclude={"references"})
        item["point_ids"] = [reference.point_id for reference in node.references]
        nodes[key] = item
    return {"nodes": nodes}


def completion(result, finish="stop"):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": json.dumps(result, ensure_ascii=False)},
                    "finish_reason": finish,
                }
            ]
        },
    )


def transport_handler(request):
    payload = json.loads(request.content)
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-only-key"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["stream"] is False
    content = json.loads(payload["messages"][1]["content"])
    if "sources" in content:
        return completion(
            {
                "points": [
                    {
                        "source_id": source["id"],
                        "kind": "definition",
                        "text": "课程定义 · " + source["text"][:300],
                        "quote": source["text"][:300],
                    }
                    for source in content["sources"]
                ]
            }
        )
    return completion(story_output(content["title"], content["confirmed_points"]))


def provider(handler=transport_handler):
    return OpenAICompatibleLLMProvider(
        "https://model.invalid/v1",
        "test-only-key",
        "test-model",
        httpx.MockTransport(handler),
    )


@pytest.fixture
def client(monkeypatch):
    async def idle():
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "worker", idle)
    monkeypatch.setattr(main, "llm_provider", provider())
    with TestClient(main.app) as client:
        assert (
            client.post(
                "/api/auth/register",
                json={
                    "email": uuid4().hex + "@example.com",
                    "password": "learning-test-password",
                },
            ).status_code
            == 200
        )
        yield client


def course(client):
    return client.post("/api/courses", json={"title": "可校对的云端课程"}).json()["id"]


def confirmed_point(client, cid):
    return client.post(
        f"/api/courses/{cid}/points",
        json={"text": "检索练习是主动回忆知识。", "confirmed": True},
    ).json()["id"]


def test_structured_drafts_batch_and_reserve_all_calls():
    budget = []
    items = provider().draft_items("检索" * 7000, reserve=budget.append)
    assert len(items) == 2
    assert len(budget) == 2 and all(value > 4096 for value in budget)
    assert all(item["kind"] == "definition" and item["quote"] for item in items)


def test_document_batches_short_blocks_with_source_binding():
    calls = []
    chunks = [
        (f"内容块 {index}", f"paragraph {index} original source") for index in range(30)
    ]
    drafts = provider().draft_document(chunks, reserve=calls.append)
    assert len(calls) == 3 and len(drafts) == 30
    for (_, source), points in zip(chunks, drafts, strict=True):
        assert points[0]["quote"] == source
    invalid = {
        "points": [
            {
                "source_id": "other-document",
                "kind": "concept",
                "text": "knowledge",
                "quote": "paragraph",
            }
        ]
    }
    with pytest.raises(providers.ProviderError, match="校验失败"):
        provider(lambda request: completion(invalid)).draft_document(chunks)


@pytest.mark.parametrize(
    "result",
    [
        {"points": []},
        {
            "points": [
                {
                    "source_id": "0:0",
                    "kind": "definition",
                    "text": "invented",
                    "quote": "不存在的引文",
                }
            ]
        },
        {
            "points": [
                {
                    "source_id": "0:0",
                    "kind": "unsupported",
                    "text": "知识",
                    "quote": "原文",
                }
            ]
        },
        {
            "points": [
                {"source_id": "0:0", "kind": "concept", "text": " ", "quote": "原文"}
            ]
        },
    ],
)
def test_drafts_reject_invalid_or_unbound_quotes(result):
    with pytest.raises(providers.ProviderError, match="校验失败"):
        provider(lambda request: completion(result)).draft_items("原文资料")


def test_story_sources_and_playability_are_application_validated():
    points = [
        {
            "text": "检索练习是主动回忆知识。",
            "reference": {
                "point_id": "owned-point",
                "file_id": "private-file",
                "file": "original.pdf",
                "location": "第1页",
                "quote": "原文引文",
            },
        }
    ]
    graph = provider().generate_story("课程", points)
    assert graph.nodes["q0"].references[0].file_id == "private-file"
    invalid = story_output("课程", points)
    invalid["nodes"]["q0"]["point_ids"] = ["other-users-point"]
    with pytest.raises(ValueError, match="未授权"):
        validated_story(invalid, points)
    invalid = story_output("课程", points)
    invalid["nodes"]["q0"]["point_ids"] = []
    with pytest.raises(ValueError, match="来源"):
        validated_story(invalid, points)
    invalid = story_output("课程", points)
    invalid["nodes"]["concept"]["choices"][0]["target"] = "success"
    with pytest.raises(ValueError, match="经过答题"):
        validated_story(invalid, points)


@pytest.mark.parametrize("status", [401, 402, 429, 500])
def test_provider_status_is_safe_and_no_hidden_fallback(status):
    model = provider(
        lambda request: httpx.Response(status, text="secret upstream diagnostic")
    )
    with pytest.raises(providers.ProviderError) as error:
        model.draft_items("原文")
    assert "secret" not in str(error.value)
    assert "test-only-key" not in str(error.value)


def test_provider_truncation_size_timeout_and_quota_guard():
    with pytest.raises(providers.ProviderError, match="未完整"):
        provider(lambda request: completion({}, finish="length")).draft_items("原文")
    with pytest.raises(providers.ProviderError, match="体积"):
        provider(
            lambda request: httpx.Response(200, content=b"x" * (1024 * 1024 + 1))
        ).draft_items("原文")

    async def slow(request):
        await asyncio.sleep(0.1)
        return completion({})

    model = provider(slow)
    model.timeout = 0.01
    with pytest.raises(providers.ProviderError, match="超时"):
        model.draft_items("原文")
    calls = []

    def denied(tokens):
        raise HTTPException(429, "budget exhausted")

    with pytest.raises(HTTPException):
        provider(lambda request: calls.append(request)).draft_items(
            "原文", reserve=denied
        )
    assert calls == []


def test_malformed_completion_envelopes_are_safe():
    for envelope in [
        None,
        [],
        {"choices": []},
        {"choices": [None]},
        {"choices": [42]},
        {"choices": [{"finish_reason": "stop", "message": None}]},
    ]:
        with pytest.raises(providers.ProviderError, match="格式无效"):
            provider(lambda request: httpx.Response(200, json=envelope)).draft_items(
                "原文"
            )


def test_missing_configuration_falls_back_to_demo(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "cloud")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert configured_learning_provider().mode == "demo"


def test_shared_usage_warns_at_global_threshold(client, monkeypatch):
    cid = course(client)
    with Session() as db:
        user_id = db.get(Course, cid).user_id
    main.reserve_model_usage(user_id, 10)
    monkeypatch.setattr(chat, "GLOBAL_REQUESTS", 1)
    usage = client.get(f"/api/courses/{cid}").json()["llm_usage"]
    assert usage["warning"] and usage["remaining_requests"] == chat.DAILY_REQUESTS - 1
    assert set(usage) == {"remaining_requests", "remaining_reserved_tokens", "warning"}


def test_cloud_upload_confirm_story_and_server_grading(client):
    cid = course(client)
    samples = make_samples(Path("test-results") / ("learning-" + uuid4().hex))
    uploaded = client.post(
        f"/api/courses/{cid}/files",
        files={"file": ("original.pdf", (samples / "original.pdf").read_bytes())},
    )
    fid = uploaded.json()["id"]
    main.process_file(fid)
    detail = client.get(f"/api/courses/{cid}").json()
    assert detail["files"][0]["mode"] == "cloud"
    assert detail["files"][0]["status"] == "ready"
    for point in detail["points"]:
        assert point["mode"] == "cloud" and point["kind"] == "definition"
        assert point["quote"] in point["source"]
        client.put(
            f'/api/courses/{cid}/points/{point["id"]}',
            json={"text": point["text"], "confirmed": True},
        )
    result = client.post(f"/api/courses/{cid}/story", json={"expected_revision": 0})
    assert result.status_code == 200 and result.json()["mode"] == "cloud"
    state = client.get(f"/api/courses/{cid}/play").json()
    assert state["mode"] == "cloud"
    for answer in ["concept", "next"]:
        state = client.post(
            f"/api/courses/{cid}/play",
            json={"choice": answer, "version": state["version"]},
        ).json()
    assert state["node"]["question"] and "correct_choice" not in state["node"]
    state = client.post(
        f"/api/courses/{cid}/play", json={"choice": "a", "version": state["version"]}
    ).json()
    assert state["score"] == 1 and state["feedback_references"]
    with Session() as db:
        account_id = db.get(Course, cid).user_id
        assert (
            db.scalar(
                select(func.sum(LLMUsage.requests)).where(
                    LLMUsage.bucket.like(f"user/{account_id}/%")
                )
            )
            >= 2
        )
        evidence = chat.retrieve(db, cid, "Retrieval practice")
        assert evidence and evidence[0]["quote"] == detail["points"][0]["quote"]


def test_partial_extraction_failure_publishes_no_chunks_or_points(client, monkeypatch):
    cid = course(client)
    fid = client.post(
        f"/api/courses/{cid}/files", files={"file": ("original.pdf", b"pending")}
    ).json()["id"]
    source = "original source " * 1000
    monkeypatch.setattr(
        main.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"chunks": [["page 1", source]]}).encode(),
        ),
    )
    calls = []

    def fail_second(request):
        calls.append(request)
        return (
            transport_handler(request)
            if len(calls) == 1
            else completion({"points": []})
        )

    monkeypatch.setattr(main, "llm_provider", provider(fail_second))
    main.process_file(fid)
    assert len(calls) == 2
    detail = client.get(f"/api/courses/{cid}").json()
    assert detail["files"][0]["status"] == "failed" and detail["points"] == []
    with Session() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.file_id == fid)
            )
            == 0
        )


def test_learning_prompts_are_private_to_owned_course(client, monkeypatch):
    own_course = course(client)
    own_point = confirmed_point(client, own_course)
    with TestClient(main.app) as other:
        other.post(
            "/api/auth/register",
            json={
                "email": uuid4().hex + "@example.com",
                "password": "other-learning-account",
            },
        )
        foreign_course = course(other)
        other.post(
            f"/api/courses/{foreign_course}/points",
            json={"text": "PRIVATE FOREIGN SOURCE", "confirmed": True},
        )
        calls = []

        def capture(request):
            calls.append(json.loads(request.content))
            return transport_handler(request)

        monkeypatch.setattr(main, "llm_provider", provider(capture))
        assert (
            client.post(f"/api/courses/{foreign_course}/story", json={}).status_code
            == 404
        )
        assert calls == []
        assert (
            client.post(f"/api/courses/{own_course}/story", json={}).status_code == 200
        )
        serialized = json.dumps(calls, ensure_ascii=False)
        assert own_point in serialized and "PRIVATE FOREIGN SOURCE" not in serialized


def test_failed_cloud_file_publishes_nothing_then_explicit_demo(client, monkeypatch):
    cid = course(client)
    samples = make_samples(Path("test-results") / ("failed-learning-" + uuid4().hex))
    monkeypatch.setattr(
        main, "llm_provider", provider(lambda request: completion({"points": []}))
    )
    fid = client.post(
        f"/api/courses/{cid}/files",
        files={"file": ("original.pdf", (samples / "original.pdf").read_bytes())},
    ).json()["id"]
    main.process_file(fid)
    detail = client.get(f"/api/courses/{cid}").json()
    assert detail["files"][0]["status"] == "failed" and detail["points"] == []
    assert (
        client.post(
            f"/api/courses/{cid}/files/{fid}/retry", json={"use_demo": True}
        ).status_code
        == 200
    )
    main.process_file(fid)
    detail = client.get(f"/api/courses/{cid}").json()
    assert (
        detail["files"][0]["mode"] == "demo" and detail["points"][0]["mode"] == "demo"
    )
    confirmed_point(client, cid)
    result = client.post(
        f"/api/courses/{cid}/story", json={"expected_revision": 0, "use_demo": True}
    )
    assert result.status_code == 200 and result.json()["mode"] == "demo"


def test_cloud_story_releases_locks_and_rejects_changed_sources(client, monkeypatch):
    cid = course(client)
    pid = confirmed_point(client, cid)
    started, release = Event(), Event()
    model = provider()
    generate = model.generate_story

    def delayed(title, points, reserve=None):
        started.set()
        assert release.wait(timeout=5)
        return generate(title, points, reserve=reserve)

    monkeypatch.setattr(model, "generate_story", delayed)
    monkeypatch.setattr(main, "llm_provider", model)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(
            client.post, f"/api/courses/{cid}/story", json={"expected_revision": 0}
        )
        assert started.wait(timeout=5)
        assert (
            client.post(
                f"/api/courses/{cid}/story", json={"expected_revision": 0}
            ).status_code
            == 409
        )
        # This edit completes while the model is waiting, proving the write lock is released.
        assert (
            client.put(
                f"/api/courses/{cid}/points/{pid}",
                json={"text": "修改后的知识", "confirmed": True},
            ).status_code
            == 200
        )
        release.set()
        assert pending.result(timeout=10).status_code == 409
    detail = client.get(f"/api/courses/{cid}").json()
    assert not detail["has_story"] and not detail["story_generating"]


def test_cloud_story_failure_and_budget_preserve_previous_version(client, monkeypatch):
    cid = course(client)
    confirmed_point(client, cid)
    assert (
        client.post(f"/api/courses/{cid}/story", json={"use_demo": True}).status_code
        == 200
    )
    monkeypatch.setattr(
        main, "llm_provider", provider(lambda request: completion({"nodes": {}}))
    )
    assert (
        client.post(
            f"/api/courses/{cid}/story", json={"expected_revision": 1}
        ).status_code
        == 502
    )
    detail = client.get(f"/api/courses/{cid}").json()
    assert detail["story_revision"] == 1 and not detail["story_generating"]
    monkeypatch.setattr(chat, "DAILY_TOKENS", 1)
    assert (
        client.post(
            f"/api/courses/{cid}/story", json={"expected_revision": 1}
        ).status_code
        == 429
    )
    assert not client.get(f"/api/courses/{cid}").json()["story_generating"]
