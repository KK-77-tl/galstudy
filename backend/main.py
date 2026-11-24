import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import time
import subprocess
import sys
from contextlib import asynccontextmanager
from uuid import uuid4
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession, defer
from .db import (
    Session,
    engine,
    migrate,
    User,
    LoginSession,
    Course,
    SourceFile,
    Chunk,
    Knowledge,
    Save,
    Attempt,
    StoryRecord,
    ChatSession,
    ChatMessage,
)
from .parsers import parse_document, ParseError
from .story import DEMO, Story
from .providers import llm_provider
from . import providers, chat
from .characters import CHARACTERS, resolve_profile
from . import workshop
from .workshop_api import build_router
from .db import ImageJob, CharacterRecord, Refund
from .security import RequestLimits
from .ocr import ocr_ready


def uid():
    return str(uuid4())


def process_file(file_id):
    token = uid()
    with Session.begin() as db:
        claimed = db.execute(
            update(SourceFile)
            .where(SourceFile.id == file_id, SourceFile.status == "queued")
            .values(
                status="processing",
                processing_token=token,
                attempts=SourceFile.attempts + 1,
            )
        )
        if claimed.rowcount != 1:
            return
    try:
        with Session() as db:
            file = db.get(SourceFile, file_id)
            if not file:
                return
            course_id = file.course_id
            mode = file.draft_mode
            user_id = db.get(Course, course_id).user_id
            payload = json.dumps(
                {"name": file.name, "data": base64.b64encode(file.data).decode()}
            ).encode()
        file = None
        result = subprocess.run(
            [sys.executable, "-m", "backend.parse_worker"],
            input=payload,
            capture_output=True,
            timeout=45,
            check=True,
        )
        del payload
        parsed = json.loads(result.stdout)
        if "error" in parsed:
            raise ParseError(parsed["error"])
        chunks = parsed["chunks"]
        provider = providers.DemoLLMProvider() if mode == "demo" else llm_provider
        if provider.mode != mode:
            raise providers.ProviderError(
                "课程生成服务配置已变化，可显式选择Demo重试。"
            )

        def reserve(tokens):
            # Recheck ownership token before every external request.
            with Session() as check:
                active = check.get(
                    SourceFile, file_id, options=[defer(SourceFile.data)]
                )
                if not active or active.processing_token != token:
                    raise providers.ProviderError("解析任务已取消。")
            return reserve_model_usage(user_id, tokens)

        per_chunk = provider.draft_document(chunks, reserve=reserve)
        drafts = [
            (location, text, items)
            for (location, text), items in zip(chunks, per_chunk, strict=True)
        ]
        with Session.begin() as db:
            if engine.dialect.name == "sqlite":
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            else:
                # Match source deletion's course lock before publishing parse output.
                db.scalar(
                    select(Course).where(Course.id == course_id).with_for_update()
                )
            file = db.get(SourceFile, file_id, options=[defer(SourceFile.data)])
            if not file or file.processing_token != token:
                return
            for location, text, items in drafts:
                chunk = Chunk(id=uid(), file_id=file.id, location=location, text=text)
                db.add(chunk)
                db.flush()
                # Explicit extractive Demo drafts retain the original source.
                for draft in items:
                    db.add(
                        Knowledge(
                            id=uid(),
                            course_id=file.course_id,
                            chunk_id=chunk.id,
                            text=draft["text"],
                            kind=draft["kind"],
                            mode=mode,
                            quote=draft["quote"],
                            confirmed=False,
                        )
                    )
            file.status = "ready"
            file.processing_token = None
    except Exception as error:
        with Session.begin() as db:
            if isinstance(error, subprocess.TimeoutExpired):
                message = "解析超过45秒已终止，请拆分文件后重试。"
            else:
                message = (
                    str(error)
                    if isinstance(error, (ParseError, providers.ProviderError))
                    else "解析任务失败，请重试或重新上传。"
                )
            if isinstance(error, HTTPException):
                message = str(error.detail)
            db.execute(
                update(SourceFile)
                .where(SourceFile.id == file_id, SourceFile.processing_token == token)
                .values(status="failed", error=message, processing_token=None)
            )


def reserve_model_usage(user_id, tokens):
    with Session() as usage_db:
        workshop.lock_user(usage_db, user_id)
        usage = chat.reserve_usage(usage_db, user_id, tokens)
        usage_db.commit()
        return usage


async def worker():
    while True:
        with Session() as db:
            pending = db.scalar(
                select(SourceFile.id).where(SourceFile.status == "queued").limit(1)
            )
        if pending:
            await asyncio.to_thread(process_file, pending)
        await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(app):
    migrate()
    workshop.seed_product()
    with Session.begin() as db:
        db.execute(
            update(SourceFile)
            .where(SourceFile.status == "processing")
            .values(status="queued", processing_token=None)
        )
        db.execute(update(Course).values(story_token=None))
        db.execute(update(Refund).where(Refund.status == "submitting").values(status="unknown", updated_at=int(time.time())))
        db.execute(
            update(ChatMessage)
            .where(ChatMessage.status == "processing")
            .values(status="failed", content="服务重启中断了回复，请重新提问。")
        )
        for job in db.scalars(select(ImageJob).where(ImageJob.status == "submitting")):
            workshop.fail_job(db, job, "提交阶段被重启中断，权益已恢复，请重试。")
    task = asyncio.create_task(worker())
    image_task = asyncio.create_task(workshop.worker())
    yield
    task.cancel()
    image_task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    try:
        await image_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="GalStudy API", lifespan=lifespan)
app.add_middleware(RequestLimits)
hasher = PasswordHasher()
APP_ORIGIN = os.getenv("APP_ORIGIN", "http://localhost:3000")


@app.middleware("http")
async def guard_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = {APP_ORIGIN, "http://127.0.0.1:3000"}
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin not in allowed
    ):
        return JSONResponse({"detail": "请求来源不被允许"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def database():
    with Session() as db:
        yield db


def user(request: Request, db: DBSession = Depends(database)):
    token = request.cookies.get("galstudy_session", "")
    session = db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires < time.time():
        raise HTTPException(401, "请先登录")
    return db.get(User, session.user_id)


def owned_course(course_id, current, db, lock=False):
    if lock and engine.dialect.name == "sqlite":
        # A write reservation serializes source changes with snapshot generation.
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    query = select(Course).where(Course.id == course_id, Course.user_id == current.id)
    if lock:
        query = query.with_for_update()
    course = db.scalar(query)
    if not course:
        raise HTTPException(404, "学习项目不存在")
    return course


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)


def set_session(account, response, db):
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token=hashlib.sha256(token.encode()).hexdigest(),
            user_id=account.id,
            expires=int(time.time()) + 604800,
        )
    )
    db.commit()
    response.set_cookie(
        "galstudy_session",
        token,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false") == "true",
        max_age=604800,
        path="/",
    )
    return {"email": account.email}


@app.get("/api/health")
def health(db: DBSession = Depends(database)):
    db.execute(select(1))
    return {
        "status": "ok",
        "mode": "Demo",
        "learning_mode": llm_provider.mode,
        "chat_mode": providers.chat_provider.mode,
        "database": engine.dialect.name,
        "ocr": ocr_ready(),
    }


@app.post("/api/auth/register")
def register(
    payload: Credentials, response: Response, db: DBSession = Depends(database)
):
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "请输入有效邮箱")
    account = User(id=uid(), email=email, password=hasher.hash(payload.password))
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "此邮箱已注册")
    return set_session(account, response, db)


@app.post("/api/auth/login")
def login(payload: Credentials, response: Response, db: DBSession = Depends(database)):
    account = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    # Verify a dummy hash too so absent accounts take a comparable path.
    digest = account.password if account else DUMMY_HASH
    try:
        valid = hasher.verify(digest, payload.password)
    except (VerifyMismatchError, InvalidHashError):
        valid = False
    if not account or not valid:
        raise HTTPException(401, "邮箱或密码错误")
    return set_session(account, response, db)


DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


@app.get("/api/auth/me")
def me(current: User = Depends(user)):
    return {
        "email": current.email,
        "selected_character_id": current.selected_character_id,
    }


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: DBSession = Depends(database)):
    token = request.cookies.get("galstudy_session", "")
    db.execute(
        delete(LoginSession).where(
            LoginSession.token == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    db.commit()
    response.delete_cookie("galstudy_session", path="/")
    return {"ok": True}


class NewCourse(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    demo: bool = False


@app.get("/api/courses")
def courses(current: User = Depends(user), db: DBSession = Depends(database)):
    return [
        {"id": c.id, "title": c.title, "demo": c.demo}
        for c in db.scalars(select(Course).where(Course.user_id == current.id))
    ]


@app.post("/api/courses")
def create_course(
    payload: NewCourse, current: User = Depends(user), db: DBSession = Depends(database)
):
    if not payload.title.strip():
        raise HTTPException(422, "项目名称不能为空")
    course = Course(
        id=uid(), user_id=current.id, title=payload.title.strip(), demo=payload.demo
    )
    db.add(course)
    db.commit()
    return {"id": course.id, "title": course.title, "demo": course.demo}


@app.get("/api/courses/{course_id}")
def get_course(
    course_id: str, current: User = Depends(user), db: DBSession = Depends(database)
):
    c = owned_course(course_id, current, db)
    files = db.scalars(
        select(SourceFile)
        .options(defer(SourceFile.data))
        .where(SourceFile.course_id == course_id)
    ).all()
    points = db.scalars(select(Knowledge).where(Knowledge.course_id == course_id)).all()
    result = []
    for p in points:
        chunk = db.get(Chunk, p.chunk_id) if p.chunk_id else None
        file = (
            db.get(SourceFile, chunk.file_id, options=[defer(SourceFile.data)])
            if chunk
            else None
        )
        result.append(
            {
                "id": p.id,
                "text": p.text,
                "confirmed": p.confirmed,
                "kind": p.kind,
                "mode": p.mode,
                "quote": p.quote,
                "location": chunk.location if chunk else "手工补充",
                "source": chunk.text if chunk else "",
                "file": file.name if file else "",
            }
        )
    latest = db.scalar(
        select(StoryRecord)
        .where(StoryRecord.course_id == course_id)
        .order_by(StoryRecord.revision.desc())
        .limit(1)
    )
    return {
        "id": c.id,
        "title": c.title,
        "demo": c.demo,
        "story_revision": latest.revision if latest else 0,
        "has_story": bool(latest) or c.demo,
        "learning_mode": llm_provider.mode,
        "ocr_enabled": ocr_ready(),
        "story_mode": latest.mode if latest else "demo",
        "story_generating": bool(c.story_token),
        "llm_usage": chat.usage_view(db, current.id),
        "files": [
            {
                "id": f.id,
                "name": f.name,
                "status": f.status,
                "error": f.error,
                "mode": f.draft_mode,
                "attempts": f.attempts,
            }
            for f in files
        ],
        "points": result,
    }


@app.post("/api/courses/{course_id}/files", status_code=202)
async def upload(
    course_id: str,
    file: UploadFile,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    owned_course(course_id, current, db)
    name = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
    if not name.lower().endswith((".pdf", ".pptx", ".docx")):
        raise HTTPException(422, "仅支持 PDF、PPTX、DOCX")
    data = await file.read(10 * 1024 * 1024 + 1)
    await file.close()
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(422, "请选择非空且不超过 10MB 的文件")
    workshop.lock_user(db, current.id)
    count = db.scalar(
        select(func.count())
        .select_from(SourceFile)
        .join(Course)
        .where(Course.user_id == current.id)
    )
    if count >= 20:
        raise HTTPException(429, "Demo 每个账号最多保存 20 个文件，请删除后重试")
    source = SourceFile(
        id=uid(),
        course_id=course_id,
        name=name,
        data=data,
        draft_mode=llm_provider.mode,
    )
    db.add(source)
    db.commit()
    return {"id": source.id, "status": "queued"}


@app.get("/api/courses/{course_id}/files/{file_id}")
def download(
    course_id: str,
    file_id: str,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    owned_course(course_id, current, db)
    file = db.scalar(
        select(SourceFile).where(
            SourceFile.id == file_id, SourceFile.course_id == course_id
        )
    )
    if not file:
        raise HTTPException(404)
    return Response(
        file.data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment"},
    )


class RetryFile(BaseModel):
    use_demo: bool = False


@app.post("/api/courses/{course_id}/files/{file_id}/retry")
def retry_file(
    course_id: str,
    file_id: str,
    payload: RetryFile | None = None,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    owned_course(course_id, current, db)
    values = {"status": "queued", "error": "", "processing_token": None}
    if payload and payload.use_demo:
        values["draft_mode"] = "demo"
    changed = db.execute(
        update(SourceFile)
        .where(
            SourceFile.id == file_id,
            SourceFile.course_id == course_id,
            SourceFile.status == "failed",
            SourceFile.attempts < 3,
        )
        .values(**values)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "仅失败任务可重试，每份文件最多尝试3次。")
    db.commit()
    return {"status": "queued"}


@app.delete("/api/courses/{course_id}/files/{file_id}")
def delete_file(
    course_id: str,
    file_id: str,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    owned_course(course_id, current, db, lock=True)
    file = db.scalar(
        select(SourceFile)
        .options(defer(SourceFile.data))
        .where(SourceFile.id == file_id, SourceFile.course_id == course_id)
    )
    if not file:
        raise HTTPException(404)
    chat_sessions = select(ChatSession.id).where(ChatSession.course_id == course_id)
    db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(chat_sessions)))
    db.execute(delete(ChatSession).where(ChatSession.course_id == course_id))
    # Source deletion purges dependent snapshots and saves so private quotes are removed.
    for record in db.scalars(
        select(StoryRecord).where(StoryRecord.course_id == course_id)
    ).all():
        graph = Story.model_validate_json(record.graph)
        if any(
            ref.file_id == file_id
            for node in graph.nodes.values()
            for ref in node.references
        ):
            db.execute(delete(Save).where(Save.story_id == record.id))
            db.execute(delete(Attempt).where(Attempt.story_id == record.id))
            db.delete(record)
    db.flush()
    chunk_ids = select(Chunk.id).where(Chunk.file_id == file_id)
    db.execute(delete(Knowledge).where(Knowledge.chunk_id.in_(chunk_ids)))
    db.execute(delete(Chunk).where(Chunk.file_id == file_id))
    db.delete(file)
    db.commit()
    return {"ok": True}


class PointInput(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    confirmed: bool = False


@app.post("/api/courses/{course_id}/points")
def add_point(
    course_id: str,
    payload: PointInput,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    owned_course(course_id, current, db, lock=True)
    point = Knowledge(
        id=uid(),
        course_id=course_id,
        text=payload.text,
        confirmed=payload.confirmed,
        mode="manual",
        kind="concept",
    )
    db.add(point)
    db.commit()
    return {"id": point.id}


@app.put("/api/courses/{course_id}/points/{point_id}")
def edit_point(
    course_id: str,
    point_id: str,
    payload: PointInput,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    owned_course(course_id, current, db, lock=True)
    point = db.scalar(
        select(Knowledge).where(
            Knowledge.id == point_id, Knowledge.course_id == course_id
        )
    )
    if not point:
        raise HTTPException(404)
    point.text, point.confirmed = payload.text, payload.confirmed
    db.commit()
    return {"ok": True}


@app.delete("/api/courses/{course_id}/points/{point_id}")
def delete_point(
    course_id: str,
    point_id: str,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    owned_course(course_id, current, db, lock=True)
    db.execute(
        delete(Knowledge).where(
            Knowledge.id == point_id, Knowledge.course_id == course_id
        )
    )
    db.commit()
    return {"ok": True}


class GenerateStory(BaseModel):
    expected_revision: int = Field(default=0, ge=0)
    use_demo: bool = False


def story_inputs(db, course_id):
    points = db.scalars(
        select(Knowledge)
        .where(Knowledge.course_id == course_id, Knowledge.confirmed == True)
        .order_by(Knowledge.id)
    ).all()
    snapshots = []
    for point in points:
        chunk = db.get(Chunk, point.chunk_id) if point.chunk_id else None
        source = (
            db.get(SourceFile, chunk.file_id, options=[defer(SourceFile.data)])
            if chunk
            else None
        )
        snapshots.append(
            {
                "text": point.text,
                "reference": {
                    "point_id": point.id,
                    "file_id": source.id if source else None,
                    "file": source.name if source else "人工补充知识点",
                    "location": chunk.location if chunk else "人工确认",
                    "quote": point.quote
                    or (chunk.text[:5000] if chunk else point.text),
                },
            }
        )
    return snapshots


@app.post("/api/courses/{course_id}/story")
def generate_story(
    course_id: str,
    payload: GenerateStory,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    course = owned_course(course_id, current, db, lock=True)
    if course.demo:
        raise HTTPException(409, "原创演示课程使用固定剧情，请创建自己的学习项目。")
    if course.story_token:
        raise HTTPException(409, "本课程正在生成剧情，请稍候并刷新项目。")
    latest = db.scalar(
        select(StoryRecord)
        .where(StoryRecord.course_id == course_id)
        .order_by(StoryRecord.revision.desc())
        .limit(1)
    )
    revision = latest.revision if latest else 0
    if revision != payload.expected_revision:
        raise HTTPException(409, "剧情版本已更新，请刷新项目后重试。")
    snapshots = story_inputs(db, course_id)
    if not 1 <= len(snapshots) <= 12:
        raise HTTPException(422, "每次支持1至12个已确认知识点，请调整确认范围。")
    provider = providers.DemoLLMProvider() if payload.use_demo else llm_provider
    token = None
    title = course.title
    try:
        if provider.mode == "cloud":
            token = uid()
            course.story_token = token
            db.commit()
            graph = provider.generate_story(
                title,
                snapshots,
                reserve=lambda tokens: reserve_model_usage(current.id, tokens),
            )
            db.expire_all()
            course = owned_course(course_id, current, db, lock=True)
            latest_revision = (
                db.scalar(
                    select(func.max(StoryRecord.revision)).where(
                        StoryRecord.course_id == course_id
                    )
                )
                or 0
            )
            if (
                course.story_token != token
                or course.title != title
                or latest_revision != revision
                or story_inputs(db, course_id) != snapshots
            ):
                raise HTTPException(
                    409, "生成期间资料或版本已变化，本次结果未发布，请核对后重试。"
                )
            course.story_token = None
        else:
            graph = provider.generate_story(title, snapshots)
        record = StoryRecord(
            id=uid(),
            course_id=course_id,
            revision=revision + 1,
            graph=graph.model_dump_json(),
            mode=provider.mode,
        )
        db.add(record)
        db.commit()
        return {
            "story_id": record.id,
            "revision": record.revision,
            "mode": record.mode,
            "nodes": len(graph.nodes),
        }
    except providers.ProviderError as error:
        raise HTTPException(502, str(error))
    except ValueError as error:
        raise HTTPException(422, str(error))
    except IntegrityError:
        raise HTTPException(409, "另一条生成请求已完成，请刷新项目。")
    finally:
        if token:
            db.rollback()
            with Session.begin() as cleanup:
                cleanup.execute(
                    update(Course)
                    .where(Course.id == course_id, Course.story_token == token)
                    .values(story_token=None)
                )


def get_save(course_id, current, db):
    course = owned_course(course_id, current, db)
    save = db.scalar(
        select(Save).where(Save.course_id == course_id, Save.user_id == current.id)
    )
    if not save:
        record = db.scalar(
            select(StoryRecord)
            .where(StoryRecord.course_id == course_id)
            .order_by(StoryRecord.revision.desc())
            .limit(1)
        )
        if not course.demo and not record:
            raise HTTPException(409, "请先确认知识点并生成剧情。")
        save = Save(
            id=uid(),
            user_id=current.id,
            course_id=course_id,
            node="start",
            score=0,
            version=0,
            story_id=record.id if record else None,
        )
        db.add(save)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            save = db.scalar(
                select(Save).where(
                    Save.course_id == course_id, Save.user_id == current.id
                )
            )
    return save


def saved_graph(save, db):
    if save.story_id is None:
        return DEMO
    record = db.get(StoryRecord, save.story_id)
    if not record or record.course_id != save.course_id:
        raise HTTPException(409, "存档对应的剧情已不可用，请回到项目重新生成。")
    return Story.model_validate_json(record.graph)


def view_save(save, db):
    graph = saved_graph(save, db)
    node = graph.nodes[save.node]
    record = db.get(StoryRecord, save.story_id) if save.story_id else None
    # Answers and question references are returned after grading to support recall.
    public_node = node.model_dump(exclude={"correct_choice", "explanation"})
    public_node["choices"] = [
        {"id": choice.id, "label": choice.label} for choice in node.choices
    ]
    if node.question:
        public_node["references"] = []
    return {
        "node_id": save.node,
        "node": public_node,
        "score": save.score,
        "version": save.version,
        "story_revision": record.revision if record else 0,
        "mode": record.mode if record else "demo",
        "total_questions": sum(n.question for n in graph.nodes.values()),
    }


@app.get("/api/courses/{course_id}/play")
def play(
    course_id: str, current: User = Depends(user), db: DBSession = Depends(database)
):
    return view_save(get_save(course_id, current, db), db)


class Action(BaseModel):
    choice: str
    version: int


@app.post("/api/courses/{course_id}/play")
def advance(
    course_id: str,
    payload: Action,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    save = get_save(course_id, current, db)
    node_id = save.node
    node = saved_graph(save, db).nodes[node_id]
    choice = next((c for c in node.choices if c.id == payload.choice), None)
    if not choice:
        raise HTTPException(422, "无效的剧情选择")
    correct = node.question and choice.id == node.correct_choice
    changed = db.execute(
        update(Save)
        .where(Save.id == save.id, Save.version == payload.version)
        .values(
            node=choice.target,
            version=Save.version + 1,
            score=Save.score + int(correct),
        )
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "存档已更新，请刷新后继续")
    if node.question:
        correct_answer = next(
            c.label for c in node.choices if c.id == node.correct_choice
        )
        db.add(
            Attempt(
                id=uid(),
                user_id=current.id,
                course_id=course_id,
                question=node.text,
                answer=choice.label,
                correct=correct,
                explanation=node.explanation,
                story_id=save.story_id,
                node_id=node_id,
                correct_answer=correct_answer,
            )
        )
    db.commit()
    db.refresh(save)
    return {
        **view_save(save, db),
        "feedback": node.explanation if node.question else "",
        "feedback_references": (
            [ref.model_dump() for ref in node.references] if node.question else []
        ),
    }


class RestartInput(BaseModel):
    version: int


@app.post("/api/courses/{course_id}/play/restart")
def restart(
    course_id: str,
    payload: RestartInput,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    save = get_save(course_id, current, db)
    latest = db.scalar(
        select(StoryRecord)
        .where(StoryRecord.course_id == course_id)
        .order_by(StoryRecord.revision.desc())
        .limit(1)
    )
    changed = db.execute(
        update(Save)
        .where(Save.id == save.id, Save.version == payload.version)
        .values(
            node="start",
            score=0,
            version=Save.version + 1,
            story_id=latest.id if latest else None,
        )
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "存档已更新，请刷新后重试。")
    db.commit()
    db.refresh(save)
    return view_save(save, db)


@app.get("/api/wrong-answers")
def wrong(current: User = Depends(user), db: DBSession = Depends(database)):
    return [
        {
            "id": a.id,
            "question": a.question,
            "answer": a.answer,
            "explanation": a.explanation,
            "reviewed": a.reviewed,
        }
        for a in db.scalars(
            select(Attempt).where(
                Attempt.user_id == current.id, Attempt.correct == False
            )
        )
    ]


@app.get("/api/wrong-answers/{attempt_id}/review")
def review_question(
    attempt_id: str, current: User = Depends(user), db: DBSession = Depends(database)
):
    attempt = db.scalar(
        select(Attempt).where(
            Attempt.id == attempt_id,
            Attempt.user_id == current.id,
            Attempt.correct == False,
        )
    )
    if not attempt:
        raise HTTPException(404, "错题不存在")
    graph = (
        Story.model_validate_json(db.get(StoryRecord, attempt.story_id).graph)
        if attempt.story_id
        else DEMO
    )
    node = graph.nodes[attempt.node_id or "quiz"]
    return {
        "question": node.text,
        "choices": [{"id": c.id, "label": c.label} for c in node.choices],
    }


class ReviewAnswer(BaseModel):
    choice: str


@app.post("/api/wrong-answers/{attempt_id}/review")
def review_answer(
    attempt_id: str,
    payload: ReviewAnswer,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    attempt = db.scalar(
        select(Attempt).where(
            Attempt.id == attempt_id,
            Attempt.user_id == current.id,
            Attempt.correct == False,
        )
    )
    if not attempt:
        raise HTTPException(404, "错题不存在")
    graph = (
        Story.model_validate_json(db.get(StoryRecord, attempt.story_id).graph)
        if attempt.story_id
        else DEMO
    )
    node = graph.nodes[attempt.node_id or "quiz"]
    if payload.choice not in {c.id for c in node.choices}:
        raise HTTPException(422, "无效答案")
    correct = payload.choice == node.correct_choice
    attempt.reviewed = correct
    db.commit()
    return {
        "correct": correct,
        "explanation": node.explanation,
        "references": [ref.model_dump() for ref in node.references],
    }


@app.get("/api/characters")
def characters(current: User = Depends(user), db: DBSession = Depends(database)):
    ids = list(CHARACTERS) + list(
        db.scalars(
            select(CharacterRecord.id).where(CharacterRecord.user_id == current.id)
        )
    )
    profiles = [resolve_profile(db, current.id, character_id) for character_id in ids]
    return [
        {
            **{
                key: value
                for key, value in profile.items()
                if key in {"id", "name", "portrait", "expressions", "tagline", "greeting", "mode"}
            },
            "selected": profile["id"] == current.selected_character_id,
        }
        for profile in profiles
    ]


class NewChat(BaseModel):
    character_id: str = "shiori"


@app.post("/api/courses/{course_id}/chat/sessions")
def create_chat(
    course_id: str,
    payload: NewChat,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    owned_course(course_id, current, db, lock=True)
    resolve_profile(db, current.id, payload.character_id)
    session = db.scalar(
        select(ChatSession).where(
            ChatSession.course_id == course_id,
            ChatSession.user_id == current.id,
            ChatSession.character_id == payload.character_id,
        )
    )
    if not session:
        session = ChatSession(
            id=uid(),
            user_id=current.id,
            course_id=course_id,
            character_id=payload.character_id,
            summary="",
        )
        db.add(session)
    db.commit()
    return {
        "id": session.id,
        "character_id": session.character_id,
        "course_id": course_id,
        "mode": providers.chat_provider.mode,
    }


def owned_chat(session_id, current, db):
    session = db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == current.id
        )
    )
    if not session:
        raise HTTPException(404, "会话不存在")
    return session


@app.get("/api/chat/sessions/{session_id}")
def get_chat(
    session_id: str, current: User = Depends(user), db: DBSession = Depends(database)
):
    session = owned_chat(session_id, current, db)
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    ).all()
    return {
        "id": session.id,
        "course_id": session.course_id,
        "character_id": session.character_id,
        "mode": providers.chat_provider.mode,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "status": m.status,
                "mode": m.mode,
                "references": json.loads(m.references),
            }
            for m in messages
        ],
    }


@app.delete("/api/chat/sessions/{session_id}")
def clear_chat(
    session_id: str, current: User = Depends(user), db: DBSession = Depends(database)
):
    session = owned_chat(session_id, current, db)
    owned_course(session.course_id, current, db, lock=True)
    db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    db.delete(session)
    db.commit()
    return {"ok": True}


class ChatInput(BaseModel):
    request_id: str = Field(min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")
    message: str = Field(min_length=1, max_length=1000)
    use_demo: bool = False


@app.post("/api/chat/sessions/{session_id}/messages")
def send_chat(
    session_id: str,
    payload: ChatInput,
    current: User = Depends(user),
    db: DBSession = Depends(database),
):
    session = owned_chat(session_id, current, db)
    owned_course(session.course_id, current, db, lock=True)
    message = payload.message.strip()
    if not message:
        raise HTTPException(422, "消息不能为空")
    provider = (
        providers.DemoLLMProvider() if payload.use_demo else providers.chat_provider
    )
    prepared = chat.prepare_chat(
        db, session, payload.request_id, message, provider.mode
    )
    return StreamingResponse(
        chat.stream_chat(prepared, provider),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


app.include_router(build_router(user))
