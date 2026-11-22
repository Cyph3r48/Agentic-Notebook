"""model selection: provider on conversations, per-user model preferences

Revision ID: 20261122_000004
Revises: 20261012_000003
Create Date: 2026-11-22 00:00:04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261122_000004"
down_revision = "20261012_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL means "infer the provider from the model name", which is how every existing row worked.
    op.add_column("conversations", sa.Column("provider", sa.String(length=20), nullable=True))
    op.create_table(
        "user_model_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("default_provider", sa.String(length=20), nullable=True),
        sa.Column("default_model", sa.String(length=100), nullable=True),
        sa.Column("enabled_models", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_model_preferences")
    op.drop_column("conversations", "provider")
