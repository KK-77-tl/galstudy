"""Course-isolated retrieval, durable chat and bounded server-side streaming."""

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer
from fastapi import HTTPException
from .db import (
    Session,
    ChatSession,
    ChatMessage,
    Knowledge,
    Chunk,
    SourceFile,
    LLMUsage,
)
from .characters import resolve_profile
from . import providers

DAILY_REQUESTS = int(os.getenv("LLM_DAILY_REQUEST_LIMIT", "50"))
GLOBAL_REQUESTS = int(os.getenv("LLM_GLOBAL_DAILY_REQUEST_LIMIT", "500"))
DAILY_TOKENS = int(os.getenv("LLM_DAILY_RESERVED_TOKEN_LIMIT", "200000"))
GLOBAL_TOKENS = int(os.getenv("LLM_GLOBAL_DAILY_RESERVED_TOKEN_LIMIT", "2000000"))
CHAT_TIMEOUT_SECONDS = float(os.getenv("LLM_CHAT_TIMEOUT_SECONDS", "30"))


def retrieve(db, course_id, question):
    normalized = question.lower()
    normalized = re.sub(r"请问|为什么|是什么|怎么|如何|一下|解释|讲解", "", normalized)
    english = re.findall(r"[a-z0-9]{2,}", normalized)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]+", normalized))
    terms = list(
        dict.fromkeys(english + [chinese[i : i + 2] for i in range(len(chinese) - 1)])
    )[:24]
    if not terms:
        return []
    ranked = []
    candidates = (
        select(Knowledge)
        .where(
            Knowledge.course_id == course_id,
            Knowledge.confirmed == True,
            or_(*(Knowledge.text.icontains(term, autoescape=True) for term in terms)),
        )
        .order_by(Knowledge.id)
        .limit(40)
    )
    for point in db.scalars(candidates):
        text = point.text.lower()
        score = sum(text.count(term) for term in terms)
        if score:
            ranked.append((score, point.id, point))
    evidence = []
    for _, _, point in sorted(ranked, reverse=True)[:3]:
        chunk = db.get(Chunk, point.chunk_id) if point.chunk_id else None
        source = (
            db.get(SourceFile, chunk.file_id, options=[defer(SourceFile.data)])
            if chunk
            else None
        )
        positions = [
            point.text.lower().find(term)
            for term in terms
            if term in point.text.lower()
        ]
        start = max(0, min(positions) - 300)
        excerpt = point.text[start : start + 1500]
        evidence.append(
            {
                "point_id": point.id,
                "file_id": source.id if source else None,
                "file": source.name if source else "人工补充知识点",
                "location": chunk.location if chunk else "人工确认",
                "quote": point.quote or (chunk.text[:1500] if chunk else excerpt),
                "text": excerpt,
            }
        )
    return evidence


def reserve_usage(db, user_id, reserved_tokens):
    day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    for bucket, requests, tokens in [
        (f"global/{day}", GLOBAL_REQUESTS, GLOBAL_TOKENS),
        (f"user/{user_id}/{day}", DAILY_REQUESTS, DAILY_TOKENS),
    ]:
        if not db.get(LLMUsage, bucket):
            try:
                with db.begin_nested():
                    db.add(LLMUsage(bucket=bucket, requests=0, reserved_tokens=0))
            except IntegrityError:
                pass
        changed = db.execute(
            update(LLMUsage)
            .where(
                LLMUsage.bucket == bucket,
                LLMUsage.requests < requests,
                LLMUsage.reserved_tokens + reserved_tokens <= tokens,
            )
            .values(
                requests=LLMUsage.requests + 1,
                reserved_tokens=LLMUsage.reserved_tokens + reserved_tokens,
            )
        )
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(429, "今日模型调用额度已用完，请明天再来。")
    db.flush()
    return usage_view(db, user_id)


def usage_view(db, user_id):
    day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    usage = db.get(LLMUsage, f"user/{user_id}/{day}", populate_existing=True)
    global_usage = db.get(LLMUsage, f"global/{day}", populate_existing=True)
    requests = usage.requests if usage else 0
    tokens = usage.reserved_tokens if usage else 0
    return {
        "remaining_requests": max(0, DAILY_REQUESTS - requests),
        "remaining_reserved_tokens": max(0, DAILY_TOKENS - tokens),
        "warning": requests >= DAILY_REQUESTS * 0.8
        or tokens >= DAILY_TOKENS * 0.8
        or bool(
            global_usage
            and (
                global_usage.requests >= GLOBAL_REQUESTS * 0.8
                or global_usage.reserved_tokens >= GLOBAL_TOKENS * 0.8
            )
        ),
    }


def prepare_chat(db, session, request_id, question, mode):
    existing = db.scalar(
        select(ChatMessage).where(
            ChatMessage.session_id == session.id,
            ChatMessage.request_id == request_id,
            ChatMessage.role == "assistant",
        )
    )
    if existing:
        raise HTTPException(409, "此消息已提交，请刷新会话查看结果。")
    pending = db.scalar(
        select(ChatMessage).where(
            ChatMessage.session_id == session.id, ChatMessage.status == "processing"
        )
    )
    if pending:
        raise HTTPException(409, "上一条消息仍在生成，请稍候。")
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id, ChatMessage.status == "complete")
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(8)
    ).all()
    history = [
        {"role": m.role, "content": m.content[:1500]} for m in reversed(messages)
    ]
    evidence = retrieve(db, session.course_id, question)
    if not evidence and re.fullmatch(
        r"(再解释一下|它是什么意思|继续讲讲|举个例子)[？?。!！ ]*", question
    ):
        previous = next(
            (
                message["content"]
                for message in reversed(history)
                if message["role"] == "user"
            ),
            None,
        )
        if previous:
            evidence = retrieve(db, session.course_id, previous)
    mode = mode if evidence else "demo"
    if session.summary:
        history.insert(
            0,
            {
                "role": "user",
                "content": "先前对话的摘录记忆，仅作上下文参考\n" + session.summary,
            },
        )
    character = resolve_profile(db, session.user_id, session.character_id)
    # Reserve a conservative UTF-8 byte upper estimate plus output and message overhead.
    reservation = (
        sum(len(m["content"].encode()) + 16 for m in history)
        + len(json.dumps(evidence, ensure_ascii=False).encode())
        + len(question.encode())
        + len(character["persona"].encode())
        + 2048
    )
    usage = reserve_usage(db, session.user_id, reservation)
    now = time.time_ns()
    user_message = ChatMessage(
        id=str(uuid4()),
        session_id=session.id,
        request_id=request_id,
        role="user",
        content=question,
        status="complete",
        references="[]",
        created_at=now,
    )
    assistant = ChatMessage(
        id=str(uuid4()),
        session_id=session.id,
        request_id=request_id,
        role="assistant",
        content="",
        status="processing",
        mode=mode,
        references=json.dumps(evidence, ensure_ascii=False),
        created_at=now + 1,
    )
    db.add_all([user_message, assistant])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "此消息已被其他请求处理，请刷新会话。")
    return {
        "message_id": assistant.id,
        "session_id": session.id,
        "character": character,
        "question": question,
        "evidence": evidence,
        "history": history,
        "usage": usage,
        "mode": mode,
    }


def event(kind, data):
    return "data: " + json.dumps({"type": kind, **data}, ensure_ascii=False) + "\n\n"


def finish_message(prepared, content, status):
    with Session.begin() as db:
        message = db.get(ChatMessage, prepared["message_id"])
        if not message:
            return False
        message.content = content
        message.status = status
        if status == "complete":
            session = db.get(ChatSession, prepared["session_id"])
            # Bounded extractive memory stays within the same course and character.
            session.summary = (
                session.summary
                + "\n学生 "
                + prepared["question"][:180]
                + "\n角色 "
                + content[:240]
            )[-1200:]
        return True


async def stream_chat(prepared, provider):
    parts = []
    yield event(
        "meta",
        {
            "mode": prepared["mode"],
            "references": prepared["evidence"],
            "usage": prepared["usage"],
        },
    )
    try:
        async with asyncio.timeout(CHAT_TIMEOUT_SECONDS):
            # Without relevant course evidence, every provider returns an explicit unknown answer.
            active_provider = (
                provider if prepared["evidence"] else providers.DemoLLMProvider()
            )
            async for fragment in active_provider.stream_chat(
                prepared["character"],
                prepared["question"],
                prepared["evidence"],
                prepared["history"],
            ):
                if sum(len(part) for part in parts) + len(fragment) > 6000:
                    raise providers.ProviderError(
                        "回复超过长度上限，已停止生成，请缩小问题范围。"
                    )
                parts.append(fragment)
                yield event("delta", {"text": fragment})
        if not parts:
            raise providers.ProviderError("模型未返回有效文本，请重试。")
        content = "".join(parts)
        if not finish_message(prepared, content, "complete"):
            yield event("error", {"message": "会话已删除，回复未保存。"})
            return
        yield event("done", {"message_id": prepared["message_id"]})
    except asyncio.CancelledError:
        finish_message(prepared, "回复已中断，请重新提问。", "failed")
        raise
    except (TimeoutError, providers.ProviderError) as error:
        message = (
            str(error)
            if isinstance(error, providers.ProviderError)
            else "模型回复超时，请稍后重试。"
        )
        finish_message(prepared, message, "failed")
        yield event("error", {"message": message})
    except Exception:
        finish_message(prepared, "陪学服务暂时不可用，请重试。", "failed")
        yield event("error", {"message": "陪学服务暂时不可用，请重试。"})
