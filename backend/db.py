import os
from pathlib import Path
from sqlalchemy import (
    create_engine,
    ForeignKey,
    String,
    Text,
    LargeBinary,
    BigInteger,
    UniqueConstraint,
    Index,
    event,
    text,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from dotenv import load_dotenv

load_dotenv()
Path("data").mkdir(exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/galstudy.db")
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    ),
)
Session = sessionmaker(engine, expire_on_commit=False)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password: Mapped[str] = mapped_column(Text)
    selected_character_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class LoginSession(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires: Mapped[int]


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    demo: Mapped[bool] = mapped_column(default=False)
    story_token: Mapped[str | None] = mapped_column(String(36), nullable=True)


class SourceFile(Base):
    __tablename__ = "source_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(default=0)
    draft_mode: Mapped[str] = mapped_column(String(20), default="demo")
    processing_token: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Chunk(Base):
    __tablename__ = "source_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"), index=True)
    location: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)


class Knowledge(Base):
    __tablename__ = "knowledge_points"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_chunks.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text)
    confirmed: Mapped[bool] = mapped_column(default=False)
    kind: Mapped[str] = mapped_column(String(20), default="excerpt")
    mode: Mapped[str] = mapped_column(String(20), default="demo")
    quote: Mapped[str] = mapped_column(Text, default="")


class StoryRecord(Base):
    __tablename__ = "stories"
    __table_args__ = (UniqueConstraint("course_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    revision: Mapped[int]
    graph: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(30), default="demo")


class Save(Base):
    __tablename__ = "saves"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    node: Mapped[str] = mapped_column(String(60), default="start")
    score: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(default=0)
    story_id: Mapped[str | None] = mapped_column(
        ForeignKey("stories.id"), nullable=True
    )


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    correct: Mapped[bool]
    explanation: Mapped[str] = mapped_column(Text)
    story_id: Mapped[str | None] = mapped_column(
        ForeignKey("stories.id"), nullable=True
    )
    node_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text, default="")
    reviewed: Mapped[bool] = mapped_column(default=False)


class Migration(Base):
    __tablename__ = "schema_migrations"
    version: Mapped[int] = mapped_column(primary_key=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (UniqueConstraint("user_id", "course_id", "character_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    character_id: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text, default="")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("session_id", "request_id", "role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="complete")
    mode: Mapped[str] = mapped_column(String(20), default="demo")
    references: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[int] = mapped_column(BigInteger)


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    bucket: Mapped[str] = mapped_column(String(100), primary_key=True)
    requests: Mapped[int] = mapped_column(default=0)
    reserved_tokens: Mapped[int] = mapped_column(default=0)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    price_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    pack_spec: Mapped[str] = mapped_column(Text)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id"),
        Index("ix_orders_real_trade", "provider", "provider_trade_id", unique=True,
              sqlite_where=text("provider <> 'mock' AND provider_trade_id IS NOT NULL"),
              postgresql_where=text("provider <> 'mock' AND provider_trade_id IS NOT NULL")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    amount_cents: Mapped[int]
    pack_spec: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str] = mapped_column(String(20), default="mock")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    provider_trade_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[int]


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[int]


class Entitlement(Base):
    __tablename__ = "entitlements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="available")
    reservation_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[int]
    updated_at: Mapped[int]


class ReferenceImage(Base):
    __tablename__ = "reference_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(24), default="pending_review")
    contains_real_person: Mapped[bool]
    rights_confirmed: Mapped[bool]
    person_consent_confirmed: Mapped[bool]
    created_at: Mapped[int]
    expires_at: Mapped[int]


class ImageJob(Base):
    __tablename__ = "image_jobs"
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    entitlement_id: Mapped[str] = mapped_column(ForeignKey("entitlements.id"))
    reference_id: Mapped[str | None] = mapped_column(
        ForeignKey("reference_images.id"), nullable=True
    )
    spec: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    remote_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int]
    updated_at: Mapped[int]


class ImageAsset(Base):
    __tablename__ = "image_assets"
    __table_args__ = (UniqueConstraint("job_id", "slot"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("image_jobs.id"), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    slot: Mapped[int]


class ImageSubmissionUsage(Base):
    __tablename__ = "image_submission_usage"
    bucket: Mapped[str] = mapped_column(String(100), primary_key=True)
    submissions: Mapped[int] = mapped_column(default=0)


class CharacterRecord(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("image_jobs.id"), unique=True)
    entitlement_id: Mapped[str] = mapped_column(
        ForeignKey("entitlements.id"), unique=True
    )
    name: Mapped[str] = mapped_column(String(40))
    persona: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(20))
    assets: Mapped[str] = mapped_column(Text)


def migrate():
    Migration.__table__.create(engine, checkfirst=True)
    migration_root = Path(__file__).parent / "migrations"
    for path in sorted(migration_root.glob(f"*.{engine.dialect.name}.sql")):
        version = int(path.name.split("_")[0])
        with engine.begin() as connection:
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            applied = connection.scalar(
                select(Migration.version).where(Migration.version == version)
            )
            if applied is not None:
                continue
            for statement in path.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    connection.execute(text(statement))
            connection.execute(Migration.__table__.insert().values(version=version))


if __name__ == "__main__":
    migrate()
