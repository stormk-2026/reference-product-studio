"""Initial local workflow schema."""

from alembic import op
from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, String

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "assets",
        Column("id", String, primary_key=True),
        Column("path", String, nullable=False),
        Column("sha256", String, nullable=False),
        Column("format", String, nullable=False),
        Column("width", Float),
        Column("height", Float),
        Column("bytes", Float),
        Column("source", String),
        Column("created_at", Float),
        Column("fixture", Boolean, nullable=False),
    )
    op.create_table(
        "jobs",
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
    op.create_table(
        "analyses",
        Column("id", String, primary_key=True),
        Column("job_id", String, ForeignKey("jobs.id")),
        Column("data", JSON, nullable=False),
        Column("version", Float),
        Column("created_at", Float),
        Column("fixture", Boolean, nullable=False),
        Column("input_ids", JSON),
    )
    op.create_table(
        "recipes",
        Column("id", String, primary_key=True),
        Column("job_id", String, ForeignKey("jobs.id")),
        Column("data", JSON, nullable=False),
        Column("version", Float),
        Column("created_at", Float),
        Column("fixture", Boolean, nullable=False),
        Column("reference_id", String),
    )
    op.create_table(
        "candidates",
        Column("id", String, primary_key=True),
        Column("job_id", String, ForeignKey("jobs.id"), unique=True),
        Column("asset_id", String, ForeignKey("assets.id")),
        Column("data", JSON, nullable=False),
        Column("created_at", Float),
        Column("favorite", Boolean),
        Column("fixture", Boolean, nullable=False),
    )
    op.create_table(
        "evaluations",
        Column("id", String, primary_key=True),
        Column("candidate_id", String, ForeignKey("candidates.id")),
        Column("data", JSON, nullable=False),
        Column("created_at", Float),
    )


def downgrade():
    for table in ["evaluations", "candidates", "recipes", "analyses", "jobs", "assets"]:
        op.drop_table(table)
