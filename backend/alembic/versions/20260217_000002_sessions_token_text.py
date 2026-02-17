"""sessions token text

Revision ID: 20260217_000002
Revises: 20260213_000001
Create Date: 2026-02-17 00:00:02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260217_000002"
down_revision = "20260213_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sessions", "session_token", existing_type=sa.String(length=255), type_=sa.Text())


def downgrade() -> None:
    op.alter_column("sessions", "session_token", existing_type=sa.Text(), type_=sa.String(length=255))
