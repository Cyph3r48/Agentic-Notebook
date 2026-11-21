"""Helpers every provider shares: history, prompt text, fallback text and safe error details."""

from __future__ import annotations

from typing import Any, Iterable

from app.core.config import settings

DEFAULT_SYSTEM_PROMPT = "You are a concise assistant. Use provided context when relevant."
REFUSAL_TEXT = "The model declined to answer this request."
NO_CONTEXT_TEXT = "I could not find relevant context in your uploaded documents."
# A failed model listing is remembered briefly so a bad key does not hit the API on every request.
MODEL_LIST_FAILURE_TTL_SECONDS = 30.0

# Fixed strings for the Test button: never the key, the URL or the provider's own error text.
TEST_DETAIL = {
    "provider_auth_error": "The provider rejected the key.",
    "provider_rate_limited": "The provider is rate limiting this key.",
    "provider_quota_exceeded": "The account has no remaining quota or credit.",
    "provider_timeout": "The provider did not answer in time.",
    "provider_http_error": "The provider returned an error.",
    "provider_error": "Could not reach the provider.",
}


def history_from_messages(
    rows: Iterable[Any],
    *,
    max_messages: int | None = None,
    max_chars: int | None = None,
) -> list[dict[str, str]]:
    """Turn stored messages into chat turns for the model.

    Skips empty rows and assistant replies that were provider fallbacks or refusals (they carry an
    `error_type`), keeps the newest `max_messages`, drops the oldest until the text fits `max_chars`,
    and makes sure the list starts with a user turn.
    """
    limit = settings.LLM_HISTORY_MESSAGES if max_messages is None else max_messages
    char_budget = settings.LLM_HISTORY_MAX_CHARS if max_chars is None else max_chars

    usable: list[dict[str, str]] = []
    for row in rows:
        role = getattr(row, "role", None)
        content = (getattr(row, "content", "") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        metadata = getattr(row, "metadata_json", None) or {}
        if role == "assistant" and metadata.get("error_type"):
            continue
        usable.append({"role": role, "content": content})

    usable = usable[-limit:] if limit > 0 else []
    while usable and sum(len(turn["content"]) for turn in usable) > char_budget:
        usable.pop(0)
    while usable and usable[0]["role"] != "user":
        usable.pop(0)
    return usable


def build_prompt(*, user_message: str, context_lines: list[str]) -> str:
    if context_lines:
        return (
            "Question:\n"
            f"{user_message}\n\n"
            "Relevant document context:\n"
            + "\n".join(context_lines[:6])
            + "\n\nAnswer based on the context when possible. If context is insufficient, say so."
        )
    return f"Question:\n{user_message}\n\nProvide a concise direct answer."


def build_messages(
    *,
    history: list[dict[str, str]] | None,
    user_message: str,
    context_lines: list[str],
) -> list[dict[str, str]]:
    prompt = build_prompt(user_message=user_message, context_lines=context_lines)
    return [*(history or []), {"role": "user", "content": prompt}]


def system_text(system_prompt: str | None) -> str:
    return (system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT


def fallback_content(context_lines: list[str]) -> str:
    if context_lines:
        return "I found relevant context in your documents:\n" + "\n".join(context_lines[:3])
    return NO_CONTEXT_TEXT
