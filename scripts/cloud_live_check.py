"""Explicitly authorized real model calls using original material and a temporary DB.

Loads local .env, uses no MockTransport, and never records credentials. Does not
perform payments, generate images, or publish private course data to a website.
"""
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
if not all(os.environ.get(k) for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")):
    raise SystemExit("Configure real model credentials before this check")
directory = ROOT / "test-results" / ("cloud-live-" + uuid4().hex)
directory.mkdir(parents=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (directory / "check.db").as_posix()
os.environ["LLM_MODE"] = "cloud"
os.environ["LLM_CHAT_MODE"] = "cloud"
os.environ["IMAGE_GENERATOR"] = "mock"
os.environ["PAYMENT_PROVIDER"] = "mock"
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend import main
from backend.db import Session, StoryRecord
from backend.story import Story

report = {"status": "running", "real_model_calls": True, "model": os.environ["LLM_MODEL"],
          "directory": str(directory), "checks": [], "samples": [], "chat": []}

def record(name, passed, **details):
    report["checks"].append({"name": name, "passed": bool(passed), **details})
    print(name, "PASS" if passed else "FAIL", flush=True)
    if not passed:
        raise AssertionError(name)

async def idle():
    await asyncio.Event().wait()

main.worker = idle

def checked(response, status=200):
    if response.status_code != status:
        raise RuntimeError(f"API status {response.status_code}: {response.text[:500]}")
    return response.json()

try:
    with TestClient(main.app) as a, TestClient(main.app) as b:
        password = "original-cloud-validation-" + uuid4().hex
        for client in (a, b):
            checked(client.post("/api/auth/register", json={"email": uuid4().hex + "@example.com", "password": password}))
        record("configured_real_learning_and_chat", main.llm_provider.mode == main.providers.chat_provider.mode == "cloud")
        cid = None
        for title, text, required in [
            ("原创学习方法", "检索练习指主动从记忆中提取知识。一个示例是合上教材，用自己的话复述刚学过的概念。检索练习后应核对原文并修正错误。", "检索"),
            ("原创速度关系", "匀速直线运动中，速度 v = s / t，其中 s 是路程，t 是时间，且 t 大于零。物体在 10 秒内匀速行进 20 米，其速度为 2 米每秒。", "速度"),
        ]:
            current = checked(a.post("/api/courses", json={"title": title}))["id"]
            doc = Document()
            doc.add_paragraph(text)
            buffer = io.BytesIO()
            doc.save(buffer)
            upload = checked(a.post(f"/api/courses/{current}/files", files={"file": ("original.docx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}), 202)
            start = time.monotonic()
            main.process_file(upload["id"])
            detail = checked(a.get(f"/api/courses/{current}"))
            file = detail["files"][0]
            record("real_draft_" + required, file["status"] == "ready" and bool(detail["points"]), error=file.get("error"), seconds=round(time.monotonic()-start, 3))
            record("owned_course_isolation_" + required, b.get(f"/api/courses/{current}").status_code == 404)
            for point in detail["points"]:
                record("verbatim_quote_" + required, bool(point["quote"]) and point["quote"] in text)
            report["samples"].append({"title": title, "source": text, "points": detail["points"]})
            if cid is None:
                cid = current
                point = next(p for p in detail["points"] if required in p["text"])
                checked(a.put(f"/api/courses/{cid}/points/{point['id']}", json={"text": point["text"], "confirmed": True}))
        start = time.monotonic()
        story_response = a.post(f"/api/courses/{cid}/story", json={"expected_revision": 0})
        report["story_seconds"] = round(time.monotonic()-start, 3)
        checked(story_response)
        with Session() as db:
            story = db.scalar(select(StoryRecord).where(StoryRecord.course_id == cid))
            graph = Story.model_validate_json(story.graph)
            report["story"] = graph.model_dump()
        record("real_validated_story", {n.chapter for n in graph.nodes.values()} == {1, 2} and sum(n.ending for n in graph.nodes.values()) >= 2, nodes=len(graph.nodes))
        state = checked(a.get(f"/api/courses/{cid}/play"))
        answered = 0
        while not state["node"]["ending"]:
            node = graph.nodes[state["node_id"]]
            choice = next(c for c in node.choices if c.id == node.correct_choice) if node.question else node.choices[0]
            answered += int(node.question)
            state = checked(a.post(f"/api/courses/{cid}/play", json={"choice": choice.id, "version": state["version"]}))
        record("real_story_played_to_ending", answered > 0 and state["score"] == answered and state["mode"] == "cloud")
        for character in ("shiori", "haruka", "rin"):
            sid = checked(a.post(f"/api/courses/{cid}/chat/sessions", json={"character_id": character}))["id"]
            start = time.monotonic()
            r = a.post(f"/api/chat/sessions/{sid}/messages", json={"request_id": str(uuid4()), "message": "检索练习是什么？请依据课程资料说明。"})
            events = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
            answer = "".join(e.get("text", "") for e in events)
            report["chat"].append({"character": character, "answer": answer, "events": events, "seconds": round(time.monotonic()-start, 3)})
            record("real_chat_" + character, r.status_code == 200 and events[-1]["type"] == "done" and events[0]["mode"] == "cloud" and "[1]" in answer and "记忆" in answer)
            record("chat_isolation_" + character, b.get(f"/api/chat/sessions/{sid}").status_code == 404)
        record("resume_cloud_story", checked(a.get(f"/api/courses/{cid}/play"))["node_id"] == state["node_id"])
    report["status"] = "passed"
except Exception as e:
    report["status"] = "failed"
    report["error"] = str(e)
    raise
finally:
    (directory / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs/cloud-live-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report:", directory / "result.json", flush=True)
