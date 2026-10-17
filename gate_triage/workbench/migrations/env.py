"""Programmatic Alembic environment for the isolated workbench tables."""
from alembic import context
from gate_triage.workbench.db import Base

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Run migrations through Database.initialize() with an explicit connection.")

context.configure(connection=connection, target_metadata=Base.metadata, version_table="wb_alembic_version")
with context.begin_transaction():
    context.run_migrations()
