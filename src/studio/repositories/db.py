import time
import uuid
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    MetaData,
    String,
    Table,
    create_engine,
    event,
)

metadata = MetaData()
assets = Table(
    "assets",
    metadata,
    Column("id", String, primary_key=True),
    Column("path", String, nullable=False),
    Column("sha256", String, nullable=False),
    Column("format", String, nullable=False),
    Column("width", Float),
    Column("height", Float),
    Column("bytes", Float),
    Column("source", String),
    Column("hidden", Boolean, nullable=False, default=False, server_default="0"),
    Column("created_at", Float),
    Column("fixture", Boolean, nullable=False),
)
jobs = Table(
    "jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("idempotency_key", String, unique=True, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("state", String, nullable=False),
    Column("phase", String),
    Column("worker_id", String),
    Column("lease_until", Float),
    Column("created_at", Float),
    Column("started_at", Float),
    Column("finished_at", Float),
    Column("error", String),
    Column("provider_request_id", String),
)
analyses = Table(
    "analyses",
    metadata,
    Column("id", String, primary_key=True),
    Column("job_id", String, ForeignKey("jobs.id")),
    Column("data", JSON, nullable=False),
    Column("version", Float),
    Column("created_at", Float),
    Column("fixture", Boolean, nullable=False),
    Column("input_ids", JSON),
)
recipes = Table(
    "recipes",
    metadata,
    Column("id", String, primary_key=True),
    Column("job_id", String, ForeignKey("jobs.id")),
    Column("data", JSON, nullable=False),
    Column("version", Float),
    Column("created_at", Float),
    Column("fixture", Boolean, nullable=False),
    Column("reference_id", String),
)
candidates = Table(
    "candidates",
    metadata,
    Column("id", String, primary_key=True),
    Column("job_id", String, ForeignKey("jobs.id"), unique=True),
    Column("asset_id", String, ForeignKey("assets.id")),
    Column("data", JSON, nullable=False),
    Column("created_at", Float),
    Column("favorite", Boolean, default=False),
    Column("fixture", Boolean, nullable=False),
)
evaluations = Table(
    "evaluations",
    metadata,
    Column("id", String, primary_key=True),
    Column("candidate_id", String, ForeignKey("candidates.id")),
    Column("data", JSON, nullable=False),
    Column("created_at", Float),
)


def identifier():
    return uuid.uuid4().hex


def engine_for(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{root / 'studio.db'}", connect_args={"timeout": 20})

    @event.listens_for(engine, "connect")
    def pragmas(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    return engine


def row(connection, table, identifier_value):
    return (
        connection.execute(table.select().where(table.c.id == identifier_value)).mappings().first()
    )


def now():
    return time.time()
