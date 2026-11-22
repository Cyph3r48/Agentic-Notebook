"""Which models a user wants in their list, and which one new conversations start on.

Preferences are a filter over what each provider really lists for this user's credentials. A saved choice
that the provider stops listing (or cannot list right now) is kept and marked unavailable, so a failed
listing never wipes what the user chose.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.schemas.model_settings import DefaultModel, ModelEntry, ModelSettingsResponse, ProviderModels
from app.services.llm.registry import PROVIDER_IDS, get_provider
from app.services.llm_service import LLMService


def _is_enabled(enabled_models: dict[str, list[str]] | None, provider: str, model_id: str) -> bool:
    if not enabled_models or provider not in enabled_models:
        return True  # no choice made for this provider: everything is on, including providers added later
    return model_id in enabled_models[provider]


class ModelSettingsService:
    def __init__(self, repo, credential_service):
        self.repo = repo
        self.credentials = credential_service

    async def _credentials_by_provider(self, user_id: UUID) -> dict[str, Any]:
        return {provider_id: await self.credentials.resolve(user_id, provider_id) for provider_id in PROVIDER_IDS}

    async def _listing(self, user_id: UUID) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        by_provider = await self._credentials_by_provider(user_id)
        return await LLMService.list_models(by_provider), by_provider

    async def get(self, user_id: UUID) -> ModelSettingsResponse:
        listing, by_provider = await self._listing(user_id)
        prefs = await self.repo.get(user_id=user_id)
        saved = (prefs.enabled_models if prefs else None) or {}

        providers: list[ProviderModels] = []
        for provider_id in PROVIDER_IDS:
            adapter = get_provider(provider_id)
            models = [
                ModelEntry(id=m["id"], name=m["name"], enabled=_is_enabled(saved, provider_id, m["id"]))
                for m in listing.get(provider_id, [])
            ]
            listed = {entry.id for entry in models}
            models += [
                ModelEntry(id=model_id, name=model_id, enabled=True, available=False)
                for model_id in saved.get(provider_id, [])
                if model_id not in listed
            ]
            providers.append(
                ProviderModels(
                    id=provider_id,
                    label=adapter.label,
                    configured=by_provider.get(provider_id) is not None or adapter.always_available,
                    models=models,
                )
            )

        default = None
        if prefs and prefs.default_provider and prefs.default_model:
            default = DefaultModel(provider=prefs.default_provider, model=prefs.default_model)
        return ModelSettingsResponse(providers=providers, default=default)

    async def update(
        self,
        user_id: UUID,
        enabled_models: dict[str, list[str]] | None,
        default: DefaultModel | None,
    ) -> ModelSettingsResponse:
        """Validate and save the full state. Raises ValueError with a message that is safe to show."""
        listing, _ = await self._listing(user_id)
        prefs = await self.repo.get(user_id=user_id)
        saved = (prefs.enabled_models if prefs else None) or {}

        cleaned: dict[str, list[str]] | None = None
        if enabled_models is not None:
            cleaned = {}
            for provider_id, ids in enabled_models.items():
                adapter = get_provider(provider_id)
                if adapter is None:
                    raise ValueError(f"Unknown provider: {provider_id}")
                allowed = {m["id"] for m in listing.get(provider_id, [])} | set(saved.get(provider_id, []))
                unknown = sorted(set(ids) - allowed)
                if unknown:
                    raise ValueError(f"These {adapter.label} models are not available to you: {unknown}")
                cleaned[provider_id] = list(dict.fromkeys(ids))

        default_provider = default_model = None
        if default is not None:
            adapter = get_provider(default.provider)
            if adapter is None:
                raise ValueError(f"Unknown provider: {default.provider}")
            known = {m["id"] for m in listing.get(default.provider, [])}
            if prefs and (prefs.default_provider, prefs.default_model) == (default.provider, default.model):
                known.add(default.model)  # an unchanged default stays valid even if the listing failed just now
            if default.model not in known:
                raise ValueError(f"The default model is not available for {adapter.label}: {default.model}")
            if not _is_enabled(cleaned, default.provider, default.model):
                raise ValueError("The default model must be one of the enabled models")
            default_provider, default_model = default.provider, default.model

        await self.repo.save(
            user_id=user_id,
            default_provider=default_provider,
            default_model=default_model,
            enabled_models=cleaned,
        )
        return await self.get(user_id)

    async def default_for(self, user_id: UUID) -> tuple[str, str] | None:
        prefs = await self.repo.get(user_id=user_id)
        if prefs and prefs.default_provider and prefs.default_model:
            return prefs.default_provider, prefs.default_model
        return None

    async def only_enabled(self, user_id: UUID, listing: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        """The user's chat list: the live listing minus models they switched off."""
        prefs = await self.repo.get(user_id=user_id)
        saved = prefs.enabled_models if prefs else None
        return {
            provider_id: [m for m in models if _is_enabled(saved, provider_id, m["id"])]
            for provider_id, models in listing.items()
        }
