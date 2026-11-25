"""Refuse to start a production server with default or missing secrets; warn loudly everywhere else.

Messages name the setting and the problem, never its value.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy.engine import make_url

from app.core.config import settings

# Values shipped in templates, compose defaults and docs. Anyone can read them, so they are not secrets.
PLACEHOLDER_SECRETS = {
    "",
    "change_me",
    "change_me_too",
    "change_me_immediately",
    "change_me_in_production",
    "generate_secure_secret_in_production",
    "generate_a_secure_random_secret_here_minimum_32_chars",
    "your_smc_admin_token_here",
}
MIN_JWT_SECRET_LENGTH = 32
MIN_ADMIN_PASSWORD_LENGTH = 10


def _is_placeholder(value: str | None) -> bool:
    return (value or "") in PLACEHOLDER_SECRETS


def find_insecure_settings() -> list[str]:
    """Human-readable problems with the current settings. Empty means nothing to fix."""
    problems: list[str] = []

    if "JWT_SECRET" not in settings.model_fields_set:
        problems.append("JWT_SECRET is not set: a random one is made on every start, so every restart signs everyone out")
    elif _is_placeholder(settings.JWT_SECRET) or len(settings.JWT_SECRET) < MIN_JWT_SECRET_LENGTH:
        problems.append(f"JWT_SECRET is a placeholder or shorter than {MIN_JWT_SECRET_LENGTH} characters, so tokens can be forged")

    if _is_placeholder(settings.ADMIN_PASSWORD) or len(settings.ADMIN_PASSWORD) < MIN_ADMIN_PASSWORD_LENGTH:
        problems.append("ADMIN_PASSWORD is a placeholder or too short")

    try:
        database_password = make_url(settings.DATABASE_URL).password
    except Exception:
        database_password = None
    if _is_placeholder(database_password):
        problems.append("The database password in DATABASE_URL (PGPASSWORD) is a placeholder or empty")

    try:
        redis_password = make_url(settings.REDIS_URL).password
    except Exception:
        redis_password = None
    if _is_placeholder(redis_password) or _is_placeholder(settings.REDIS_PASSWORD):
        problems.append("The Redis password (REDIS_PASSWORD) is a placeholder or empty")

    return problems


def check_startup_security() -> list[str]:
    """Raise in production when any problem is found; otherwise log each as a warning. Returns the problems."""
    problems = find_insecure_settings()
    if settings.ENVIRONMENT.lower() == "production":
        if problems:
            raise RuntimeError(
                "Refusing to start in production with insecure settings:\n- " + "\n- ".join(problems)
            )
        return problems
    for problem in problems:
        logger.warning("Insecure setting (fine for local use, never for a shared server): {problem}", problem=problem)
    return problems
