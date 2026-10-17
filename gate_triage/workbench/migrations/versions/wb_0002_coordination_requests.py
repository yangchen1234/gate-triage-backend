"""Persist internal coordination requests separately from provider facts.

Revision ID: wb_0002
Revises: wb_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "wb_0002"
down_revision = "wb_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wb_coordination_requests",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("owner_role", sa.String(length=80), nullable=False),
        sa.Column("service_kind", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("container_ids", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'resolved')", name="ck_wb_request_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["wb_workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wb_coordination_requests_workspace_id", "wb_coordination_requests", ["workspace_id"])
    op.create_index("ix_wb_coordination_requests_status", "wb_coordination_requests", ["status"])


def downgrade():
    op.drop_index("ix_wb_coordination_requests_status", table_name="wb_coordination_requests")
    op.drop_index("ix_wb_coordination_requests_workspace_id", table_name="wb_coordination_requests")
    op.drop_table("wb_coordination_requests")
