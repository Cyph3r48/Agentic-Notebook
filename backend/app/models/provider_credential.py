"""Per-user provider credentials. API keys are stored encrypted, never in plaintext."""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProviderCredential(Base, TimestampMixin):
    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_provider_credentials_user_provider"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    # Fernet token from SecretBox, bound to "<user id>:<provider>". Null when only a base URL is saved.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Last four characters of the key, so the UI can show which key is saved without decrypting it.
    key_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
