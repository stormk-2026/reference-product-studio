"""Hide library assets without destroying historical job inputs."""

from alembic import op
from sqlalchemy import Boolean, Column

revision = "0002"
down_revision = "0001"


def upgrade():
    op.add_column("assets", Column("hidden", Boolean, nullable=False, server_default="0"))


def downgrade():
    op.drop_column("assets", "hidden")
