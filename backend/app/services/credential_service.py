"""Resolve, save and test per-user provider credentials.

Keys are encrypted with `SecretBox` before they reach the database and are decrypted only to make a provider
call or a connection test. Nothing here returns, logs or caches a plaintext key beyond the request that needs it.
"""

from __future__ import annotations

from uuid import UUID

from loguru import logger

from app.core.config import settings
from app.core.secret_box import SecretBox, SecretDecryptError, SecretsNotConfigured, get_secret_box
from app.schemas.provider_settings import PROVIDERS, ProviderStatus
from app.services.llm_service import LLMService, ProviderCredentials

# Providers that have an adapter today. OpenAI keys can be stored already; the adapter is a later ticket.
SUPPORTED_PROVIDERS = {"anthropic", "ollama"}


def _context(user_id: UUID | str, provider: str) -> str:
    return f"{user_id}:{provider}"


class CredentialService:
    def __init__(self, repo, box: SecretBox | None = None):
        self.repo = repo
        self._box = box

    @property
    def box(self) -> SecretBox:
        return self._box if self._box is not None else get_secret_box()

    # ------------------------------------------------------------------
    # Resolve: what a provider call should use
    # ------------------------------------------------------------------

    async def resolve(self, user_id: UUID, provider: str) -> ProviderCredentials | None:
        """The user's own credentials, else the server-wide Claude key (if allowed), else None.

        None means "use the server settings as they are": for Ollama that is `OLLAMA_URL` and no key.
        """
        row = await self.repo.get(user_id=user_id, provider=provider)
        if row is not None and (row.api_key_encrypted or row.base_url):
            api_key = None
            if row.api_key_encrypted:
                try:
                    api_key = self.box.decrypt(row.api_key_encrypted, context=_context(user_id, provider))
                except (SecretDecryptError, SecretsNotConfigured):
                    logger.warning(
                        "Saved {provider} key for user {user_id} cannot be decrypted; ask the user to enter it again",
                        provider=provider,
                        user_id=str(user_id),
                    )
            if api_key or row.base_url:
                return ProviderCredentials(api_key=api_key, base_url=row.base_url, source="user", owner=str(user_id))

        if provider == "anthropic" and settings.ALLOW_SERVER_PROVIDER_KEYS and settings.CLAUDE_API_KEY:
            return ProviderCredentials(api_key=settings.CLAUDE_API_KEY, source="server")
        return None

    # ------------------------------------------------------------------
    # Status: what the Settings page shows. Never contains a key.
    # ------------------------------------------------------------------

    async def status(self, user_id: UUID) -> list[ProviderStatus]:
        rows = {row.provider: row for row in await self.repo.list_for_user(user_id=user_id)}
        return [self._status_for(user_id, provider, rows.get(provider)) for provider in PROVIDERS]

    async def status_for(self, user_id: UUID, provider: str) -> ProviderStatus:
        return self._status_for(user_id, provider, await self.repo.get(user_id=user_id, provider=provider))

    def _status_for(self, user_id: UUID, provider: str, row) -> ProviderStatus:
        has_key = False
        needs_reentry = False
        if row is not None and row.api_key_encrypted:
            try:
                self.box.decrypt(row.api_key_encrypted, context=_context(user_id, provider))
                has_key = True
            except (SecretDecryptError, SecretsNotConfigured):
                needs_reentry = True
        has_url = bool(row is not None and row.base_url)

        if has_key or has_url:
            source = "user"
        elif provider == "anthropic" and settings.ALLOW_SERVER_PROVIDER_KEYS and settings.CLAUDE_API_KEY:
            source = "server"
        elif provider == "ollama":
            source = "server"  # the server's OLLAMA_URL is always available
        else:
            source = "none"

        return ProviderStatus(
            provider=provider,
            configured=source != "none",
            source=source,
            key_hint=row.key_hint if has_key else None,
            base_url=row.base_url if has_url else None,
            needs_reentry=needs_reentry,
            supported=provider in SUPPORTED_PROVIDERS,
            updated_at=row.updated_at if row is not None else None,
        )

    # ------------------------------------------------------------------
    # Save, delete, test
    # ------------------------------------------------------------------

    async def save(
        self,
        user,
        provider: str,
        *,
        api_key: str | None,
        base_url: str | None,
        base_url_provided: bool,
    ) -> ProviderStatus:
        """Store a key and/or an Ollama base URL. Omitted fields keep their saved value.

        Raises ValueError (bad request), PermissionError (not allowed) or SecretsNotConfigured (no master key).
        """
        if provider not in PROVIDERS:
            raise ValueError("Unknown provider")
        if api_key is None and not base_url_provided:
            raise ValueError("Nothing to save: send an api_key and/or a base_url")
        if base_url_provided:
            if provider != "ollama":
                raise ValueError("Only Ollama has a base URL")
            if getattr(user, "role", None) != "admin":
                raise PermissionError("Only an admin can set the Ollama URL")

        token = hint = None
        if api_key is not None:
            token = self.box.encrypt(api_key, context=_context(user.id, provider))  # may raise SecretsNotConfigured
            hint = api_key[-4:]

        await self.repo.upsert(
            user_id=user.id,
            provider=provider,
            api_key_encrypted=token,
            key_hint=hint,
            base_url=base_url,
            replace_key=api_key is not None,
            replace_url=base_url_provided,
        )
        logger.bind(action="provider_credential_saved", user_id=str(user.id), provider=provider).info(
            "Provider credential saved key={key} url={url}", key=api_key is not None, url=base_url_provided
        )
        return await self.status_for(user.id, provider)

    async def delete(self, user_id: UUID, provider: str) -> bool:
        removed = await self.repo.delete(user_id=user_id, provider=provider)
        if removed:
            logger.bind(action="provider_credential_deleted", user_id=str(user_id), provider=provider).info(
                "Provider credential deleted"
            )
        return removed

    async def test(self, user_id: UUID, provider: str) -> dict:
        return await LLMService.test_connection(provider, await self.resolve(user_id, provider))
