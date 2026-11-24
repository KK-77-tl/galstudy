import os
from pathlib import Path
from uuid import uuid4

TEST_ROOT = Path(os.environ["GALSTUDY_TEST_ROOT"])

import pytest
from fastapi.testclient import TestClient
from backend.main import app, process_file
from backend.parsers import parse_document, ParseError
from backend.story import DEMO, Story
from backend.providers import DemoLLMProvider
from scripts.make_samples import make_samples


def finish_parse(client, course_id, file_id):
    import time

    process_file(file_id)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        files = client.get(f"/api/courses/{course_id}").json()["files"]
        file = next(item for item in files if item["id"] == file_id)
        if file["status"] in {"ready", "failed"}:
            return file
        time.sleep(0.02)
    raise AssertionError("Parser did not reach a terminal state")


@pytest.fixture(scope="module")
def samples():
    return make_samples(TEST_ROOT / "samples")


@pytest.mark.parametrize(
    "ext,source", [("pdf", "第 1 页"), ("pptx", "幻灯片 1"), ("docx", "内容块 1")]
)
def test_original_parsers(samples, ext, source):
    chunks = parse_document(
        "original." + ext, (samples / ("original." + ext)).read_bytes()
    )
    assert source in chunks[0][0]
    assert "Study methods" in chunks[0][1]
    assert any("|" in text for _, text in chunks)
    if ext != "pdf":
        assert any("学习方法" in text for _, text in chunks)


def test_parse_failures(samples):
    for name, data in [
        ("empty.pdf", b""),
        ("wrong.exe", b"a"),
        ("bad.docx", b"not zip"),
    ]:
        with pytest.raises(ParseError):
            parse_document(name, data)
    with pytest.raises(ParseError, match="OCR"):
        parse_document("scan.pdf", (samples / "no-text.pdf").read_bytes())


def test_ocr_extension_and_full_demo_draft(samples):
    class TestOCR:
        def extract_pdf_page(self, data, page_number):
            assert page_number == 1
            return "OCR extension test"

    assert (
        parse_document("scan.pdf", (samples / "no-text.pdf").read_bytes(), TestOCR())[
            0
        ][1]
        == "OCR extension test"
    )
    text = "Original knowledge " * 300
    assert "".join(DemoLLMProvider().draft_knowledge(text)) == text


def test_graph():
    assert DEMO.nodes["quiz"].chapter == 2
    assert {c.target for c in DEMO.nodes["start"].choices} == {"concept", "practice"}
    broken = DEMO.model_dump()
    broken["nodes"]["start"]["choices"][0]["target"] = "missing"
    with pytest.raises(ValueError):
        Story.model_validate(broken)
    invalid = DEMO.model_dump()
    invalid["nodes"]["quiz"]["correct_choice"] = "missing"
    with pytest.raises(ValueError):
        Story.model_validate(invalid)
    cyclic = DEMO.model_dump()
    cyclic["nodes"]["concept"]["choices"].append(
        {"id": "loop", "label": "Repeat", "target": "start"}
    )
    with pytest.raises(ValueError, match="Cyclic"):
        Story.model_validate(cyclic)


def chat_events(response):
    import json

    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_chat_retrieval_isolation_history_and_quota(monkeypatch):
    from backend import chat, providers
    from backend.db import Session, ChatSession

    with TestClient(app) as a, TestClient(app) as b:
        for client, name in [(a, "chat-a"), (b, "chat-b")]:
            client.post(
                "/api/auth/register",
                json={"email": name + "@example.com", "password": "original-demo-pass"},
            )
        assert len(a.get("/api/characters").json()) == 3
        cid = a.post("/api/courses", json={"title": "课程聊天"}).json()["id"]
        other = a.post("/api/courses", json={"title": "其他课程"}).json()["id"]
        a.post(
            f"/api/courses/{cid}/points",
            json={"text": "检索练习是主动回忆知识。", "confirmed": True},
        )
        a.post(
            f"/api/courses/{cid}/points",
            json={"text": "火星秘密 UNCONFIRMED", "confirmed": False},
        )
        a.post(
            f"/api/courses/{other}/points",
            json={"text": "火星秘密 OTHER COURSE", "confirmed": True},
        )
        path = f"/api/courses/{cid}/chat/sessions"
        assert b.post(path, json={}).status_code == 404
        sid = a.post(path, json={}).json()["id"]
        assert a.post(path, json={}).json()["id"] == sid
        endpoint = f"/api/chat/sessions/{sid}"
        assert b.get(endpoint).status_code == 404
        assert b.delete(endpoint).status_code == 404
        request_id = str(uuid4())
        response = a.post(
            endpoint + "/messages",
            json={"request_id": request_id, "message": "检索练习是什么？"},
        )
        events = chat_events(response)
        assert events[-1]["type"] == "done"
        assert events[0]["mode"] == "demo" and events[0]["references"]
        answer = "".join(event.get("text", "") for event in events)
        assert "主动回忆" in answer and "UNCONFIRMED" not in answer
        assert (
            a.post(
                endpoint + "/messages",
                json={"request_id": request_id, "message": "检索练习是什么？"},
            ).status_code
            == 409
        )
        assert len(a.get(endpoint).json()["messages"]) == 2
        response = a.post(
            endpoint + "/messages",
            json={"request_id": str(uuid4()), "message": "火星秘密是什么？"},
        )
        assert not chat_events(response)[0]["references"]
        assert "不能确定" in response.text and "OTHER COURSE" not in response.text
        haruka = a.post(path, json={"character_id": "haruka"}).json()["id"]
        response = a.post(
            f"/api/chat/sessions/{haruka}/messages",
            json={"request_id": str(uuid4()), "message": "检索练习"},
        )
        assert "先找依据" in response.text and haruka != sid
        assert len(a.get(endpoint).json()["messages"]) == 4
        with Session() as db:
            assert db.get(ChatSession, sid).summary
        monkeypatch.setattr(chat, "DAILY_REQUESTS", 4)
        warning = a.post(
            endpoint + "/messages",
            json={"request_id": str(uuid4()), "message": "检索练习"},
        )
        assert chat_events(warning)[0]["usage"]["warning"]
        assert (
            a.post(
                endpoint + "/messages",
                json={"request_id": str(uuid4()), "message": "检索练习"},
            ).status_code
            == 429
        )
        assert len(a.get(endpoint).json()["messages"]) == 6
        assert a.delete(endpoint).status_code == 200
        assert a.get(endpoint).status_code == 404


def test_chat_failure_and_explicit_demo_fallback(monkeypatch):
    import asyncio
    from backend import providers, chat

    class FailingProvider:
        mode = "cloud"

        async def stream_chat(self, *args):
            raise providers.ProviderError("模型额度不足，请切换 Demo。")
            yield ""

    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={
                "email": "chat-failure@example.com",
                "password": "original-demo-pass",
            },
        )
        cid = client.post("/api/courses", json={"title": "错误处理"}).json()["id"]
        client.post(
            f"/api/courses/{cid}/points",
            json={"text": "检索练习是主动回忆知识。", "confirmed": True},
        )
        sid = client.post(f"/api/courses/{cid}/chat/sessions", json={}).json()["id"]
        endpoint = f"/api/chat/sessions/{sid}"
        monkeypatch.setattr(providers, "chat_provider", FailingProvider())
        response = client.post(
            endpoint + "/messages",
            json={"request_id": str(uuid4()), "message": "检索练习"},
        )
        assert chat_events(response)[-1]["type"] == "error"
        assert client.get(endpoint).json()["messages"][-1]["status"] == "failed"
        response = client.post(
            endpoint + "/messages",
            json={"request_id": str(uuid4()), "message": "检索练习", "use_demo": True},
        )
        assert (
            chat_events(response)[0]["mode"] == "demo"
            and chat_events(response)[-1]["type"] == "done"
        )

        class SlowProvider:
            mode = "cloud"

            async def stream_chat(self, *args):
                await asyncio.sleep(1)
                yield "late"

        monkeypatch.setattr(providers, "chat_provider", SlowProvider())
        monkeypatch.setattr(chat, "CHAT_TIMEOUT_SECONDS", 0.01)
        response = client.post(
            endpoint + "/messages",
            json={"request_id": str(uuid4()), "message": "检索练习"},
        )
        assert "超时" in response.text
        assert client.get(endpoint).json()["messages"][-1]["status"] == "failed"


def test_cloud_chat_transport():
    import asyncio, json, httpx
    from backend.providers import OpenAICompatibleChatProvider, ProviderError
    from backend.characters import CHARACTERS

    async def run():
        def handler(request):
            payload = json.loads(request.content)
            assert payload["stream"] and payload["max_tokens"] == 512
            assert request.headers["authorization"] == "Bearer test-key"
            return httpx.Response(
                200,
                content='data: {"choices":[{"delta":{"content":"资料依据 [1]"}}]}\n\ndata: [DONE]\n\n',
            )

        provider = OpenAICompatibleChatProvider(
            "https://example.test/v1",
            "test-key",
            "test-model",
            httpx.MockTransport(handler),
        )
        fragments = [
            part
            async for part in provider.stream_chat(
                CHARACTERS["shiori"], "问题", [{"text": "资料"}], []
            )
        ]
        assert "".join(fragments) == "资料依据 [1]"
        provider = OpenAICompatibleChatProvider(
            "https://example.test/v1",
            "test-key",
            "test-model",
            httpx.MockTransport(lambda request: httpx.Response(429)),
        )
        with pytest.raises(ProviderError, match="额度"):
            async for _ in provider.stream_chat(CHARACTERS["shiori"], "问题", [], []):
                pass

    asyncio.run(run())


def test_source_delete_serializes_with_story_generation(samples, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from backend.providers import llm_provider

    started, release = Event(), Event()
    original = llm_provider.generate_story

    def delayed_generate(title, points):
        started.set()
        assert release.wait(timeout=5)
        return original(title, points)

    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"email": "race@example.com", "password": "original-demo-pass"},
        )
        cid = client.post("/api/courses", json={"title": "并发删除测试"}).json()["id"]
        fid = client.post(
            f"/api/courses/{cid}/files",
            files={"file": ("original.pdf", (samples / "original.pdf").read_bytes())},
        ).json()["id"]
        finish_parse(client, cid, fid)
        point = client.get(f"/api/courses/{cid}").json()["points"][0]
        client.put(
            f'/api/courses/{cid}/points/{point["id"]}',
            json={"text": point["text"], "confirmed": True},
        )
        monkeypatch.setattr(llm_provider, "generate_story", delayed_generate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            generation = pool.submit(
                client.post, f"/api/courses/{cid}/story", json={"expected_revision": 0}
            )
            assert started.wait(timeout=5)
            deletion = pool.submit(client.delete, f"/api/courses/{cid}/files/{fid}")
            release.set()
            assert generation.result(timeout=10).status_code == 200
            assert deletion.result(timeout=10).status_code == 200
        detail = client.get(f"/api/courses/{cid}").json()
        assert not detail["has_story"] and not detail["files"]


def test_course_story_lifecycle(samples):
    with TestClient(app) as a, TestClient(app) as b:
        for client, name in [(a, "story-a"), (b, "story-b")]:
            assert (
                client.post(
                    "/api/auth/register",
                    json={
                        "email": name + "@example.com",
                        "password": "original-demo-pass",
                    },
                ).status_code
                == 200
            )
        cid = a.post("/api/courses", json={"title": "自己的课件"}).json()["id"]
        story_path = f"/api/courses/{cid}/story"
        play_path = f"/api/courses/{cid}/play"
        assert a.post(story_path, json={}).status_code == 422
        assert b.post(story_path, json={}).status_code == 404
        fid = a.post(
            f"/api/courses/{cid}/files",
            files={"file": ("original.docx", (samples / "original.docx").read_bytes())},
        ).json()["id"]
        finish_parse(a, cid, fid)
        point = a.get(f"/api/courses/{cid}").json()["points"][0]
        a.put(
            f'/api/courses/{cid}/points/{point["id"]}',
            json={"text": "检索练习是主动回忆知识。", "confirmed": True},
        )
        a.post(
            f"/api/courses/{cid}/points",
            json={"text": "间隔学习分散安排复习。", "confirmed": True},
        )
        a.post(
            f"/api/courses/{cid}/points",
            json={"text": "UNCONFIRMED SECRET", "confirmed": False},
        )
        generated = a.post(story_path, json={"expected_revision": 0})
        assert generated.status_code == 200
        assert generated.json()["revision"] == 1
        state = a.get(play_path).json()
        assert state["total_questions"] == 2
        state = a.post(
            play_path, json={"choice": "concept", "version": state["version"]}
        ).json()
        assert state["node_id"] == "concept"
        assert state["node"]["references"]
        assert "UNCONFIRMED SECRET" not in str(state)
        # A new story version keeps the in-progress save on its immutable snapshot.
        assert a.post(story_path, json={"expected_revision": 1}).status_code == 200
        assert a.post(story_path, json={"expected_revision": 1}).status_code == 409
        assert a.get(play_path).json()["story_revision"] == 1
        state = a.post(
            play_path, json={"choice": "next", "version": state["version"]}
        ).json()
        assert "correct_choice" not in state["node"]
        assert all("target" not in choice for choice in state["node"]["choices"])
        assert state["node"]["references"] == []
        state = a.post(
            play_path, json={"choice": "b", "version": state["version"]}
        ).json()
        assert state["feedback"] and state["feedback_references"]
        state = a.post(
            play_path, json={"choice": "next", "version": state["version"]}
        ).json()
        state = a.post(
            play_path, json={"choice": "b", "version": state["version"]}
        ).json()
        assert state["node"]["ending"] and state["score"] == 1
        wrong = a.get("/api/wrong-answers").json()[0]
        review = f'/api/wrong-answers/{wrong["id"]}/review'
        assert b.get(review).status_code == 404
        assert b.post(review, json={"choice": "a"}).status_code == 404
        assert a.post(review, json={"choice": "invalid"}).status_code == 422
        assert a.post(review, json={"choice": "a"}).json()["correct"]
        assert a.get("/api/wrong-answers").json()[0]["reviewed"]
        restarted = a.post(
            play_path + "/restart", json={"version": state["version"]}
        ).json()
        assert restarted["node_id"] == "start" and restarted["score"] == 0
        assert restarted["story_revision"] == 2
        assert (
            a.post(
                play_path + "/restart", json={"version": state["version"]}
            ).status_code
            == 409
        )
        chat_id = a.post(f"/api/courses/{cid}/chat/sessions", json={}).json()["id"]
        a.post(
            f"/api/chat/sessions/{chat_id}/messages",
            json={"request_id": str(uuid4()), "message": "检索练习"},
        )
        assert a.delete(f"/api/courses/{cid}/files/{fid}").status_code == 200
        assert a.get(f"/api/chat/sessions/{chat_id}").status_code == 404
        assert not a.get(f"/api/courses/{cid}").json()["has_story"]
        assert a.get(play_path).status_code == 409
        assert a.get("/api/wrong-answers").json() == []


def test_full_api_and_isolation(samples):
    with TestClient(app) as a, TestClient(app) as b:
        assert a.get("/api/courses").status_code == 401
        for client, name in [(a, "a"), (b, "b")]:
            result = client.post(
                "/api/auth/register",
                json={"email": name + "@example.com", "password": "original-demo-pass"},
            )
            assert result.status_code == 200
            assert "HttpOnly" in result.headers["set-cookie"]
        course = a.post(
            "/api/courses", json={"title": "Original course", "demo": True}
        ).json()
        cid = course["id"]
        assert b.get("/api/courses").json() == []
        assert b.get(f"/api/courses/{cid}").status_code == 404
        assert b.get(f"/api/courses/{cid}/play").status_code == 404
        for ext in ["docx", "pptx", "pdf"]:
            result = a.post(
                f"/api/courses/{cid}/files",
                files={
                    "file": (
                        "original." + ext,
                        (samples / ("original." + ext)).read_bytes(),
                    )
                },
            )
            assert result.status_code == 202
            fid = result.json()["id"]
            finish_parse(a, cid, fid)
            assert b.get(f"/api/courses/{cid}/files/{fid}").status_code == 404
            assert b.delete(f"/api/courses/{cid}/files/{fid}").status_code == 404
            assert a.get(f"/api/courses/{cid}/files/{fid}").status_code == 200
        detail = a.get(f"/api/courses/{cid}").json()
        assert all(f["status"] == "ready" for f in detail["files"])
        point = detail["points"][0]
        path = f'/api/courses/{cid}/points/{point["id"]}'
        assert (
            b.put(path, json={"text": "Intrusion", "confirmed": True}).status_code
            == 404
        )
        assert (
            a.put(
                path, json={"text": "Edited knowledge", "confirmed": True}
            ).status_code
            == 200
        )
        assert a.get(f"/api/courses/{cid}").json()["points"][0]["confirmed"]
        assert (
            a.post(
                f"/api/courses/{cid}/files", files={"file": ("empty.pdf", b"")}
            ).status_code
            == 422
        )
        assert (
            a.post(
                f"/api/courses/{cid}/files", files={"file": ("bad.exe", b"x")}
            ).status_code
            == 422
        )
        failed = a.post(
            f"/api/courses/{cid}/files",
            files={"file": ("scan.pdf", (samples / "no-text.pdf").read_bytes())},
        ).json()["id"]
        finish_parse(a, cid, failed)
        retry_path = f"/api/courses/{cid}/files/{failed}/retry"
        assert b.post(retry_path).status_code == 404
        for _ in range(2):
            assert a.post(retry_path).status_code == 200
            finish_parse(a, cid, failed)
        assert a.post(retry_path).status_code == 409
        play = f"/api/courses/{cid}/play"
        state = a.get(play).json()
        assert state["node_id"] == "start"
        result = a.post(play, json={"choice": "concept", "version": state["version"]})
        assert result.json()["node_id"] == "concept"
        assert a.post(play, json={"choice": "next", "version": 0}).status_code == 409
        assert (
            a.post(play, json={"choice": "next", "version": 1}).json()["node_id"]
            == "quiz"
        )
        assert (
            a.post(play, json={"choice": "recall", "version": 2}).json()["score"] == 1
        )
        assert a.post(play, json={"choice": "recall", "version": 3}).status_code == 422
        a.post("/api/auth/logout")
        assert a.get(play).status_code == 401
        assert (
            a.post(
                "/api/auth/login",
                json={"email": "a@example.com", "password": "original-demo-pass"},
            ).status_code
            == 200
        )
        assert a.get(play).json()["node_id"] == "success"
        second = a.post(
            "/api/courses", json={"title": "Wrong branch", "demo": True}
        ).json()["id"]
        path = f"/api/courses/{second}/play"
        a.get(path)
        for version, choice in enumerate(["practice", "next", "reread"]):
            result = a.post(path, json={"choice": choice, "version": version})
            assert result.status_code == 200
        assert result.json()["node_id"] == "review"
        assert len(a.get("/api/wrong-answers").json()) == 1
        assert b.get("/api/wrong-answers").json() == []
        assert (
            a.post(
                "/api/courses",
                json={"title": "Bad"},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
