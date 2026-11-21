"""provider credentials

Revision ID: 20261012_000003
Revises: 20260217_000002
Create Date: 2026-10-12 00:00:03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261012_000003"
down_revision = "20260217_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("key_hint", sa.String(length=8), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_provider_credentials_user_provider"),
    )
    op.create_index("ix_provider_credentials_user_id", "provider_credentials", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_provider_credentials_user_id", table_name="provider_credentials")
    op.drop_table("provider_credentials")
