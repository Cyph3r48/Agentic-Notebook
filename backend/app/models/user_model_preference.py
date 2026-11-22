"""Which models a user wants to see and which one new conversations start on."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserModelPreference(Base):
    __tablename__ = "user_model_preferences"

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    default_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # {provider id: [model ids]}. NULL, or a provider that is absent, means every model of that provider is enabled.
    enabled_models: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
