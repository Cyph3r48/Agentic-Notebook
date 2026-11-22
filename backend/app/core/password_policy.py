"""Rules for a new password. The message is safe to show; it never contains the password."""

from __future__ import annotations

from app.core.startup_checks import PLACEHOLDER_SECRETS

MIN_NEW_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256


def check_new_password(new_password: str, current_password: str) -> str | None:
    """None when acceptable, else what is wrong."""
    if len(new_password) < MIN_NEW_PASSWORD_LENGTH:
        return f"The new password must be at least {MIN_NEW_PASSWORD_LENGTH} characters"
    if len(new_password) > MAX_PASSWORD_LENGTH:
        return f"The new password must be at most {MAX_PASSWORD_LENGTH} characters"
    if new_password == current_password:
        return "The new password must be different from the current one"
    if new_password in PLACEHOLDER_SECRETS or new_password.strip() == "":
        return "That password is a well-known placeholder; choose another"
    return None
