from alembic import context

from studio.config import data_dir
from studio.repositories.db import engine_for, metadata

with engine_for(data_dir()).connect() as connection:
    context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
