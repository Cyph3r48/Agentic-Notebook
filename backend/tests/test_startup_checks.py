from __future__ import annotations

import pytest
from loguru import logger

from app.core import startup_checks
from app.core.config import settings
from app.core.password_policy import check_new_password
from app.core.startup_checks import check_startup_security, find_insecure_settings

GOOD = {
    "ENVIRONMENT": "production",
    "JWT_SECRET": "j" * 40,
    "ADMIN_PASSWORD": "a-long-admin-passphrase",
    "DATABASE_URL": "postgresql+asyncpg://si:Str0ng-db-pass@postgres:5432/si",
    "REDIS_URL": "redis://:Str0ng-redis-pass@redis:6379/0",
    "REDIS_PASSWORD": "Str0ng-redis-pass",
}


@pytest.fixture
def secure(monkeypatch):
    """Settings that pass every check, with JWT_SECRET counted as explicitly set."""
    for name, value in GOOD.items():
        monkeypatch.setattr(settings, name, value)
    fields = set(settings.model_fields_set) | {"JWT_SECRET"}
    monkeypatch.setattr(settings, "__pydantic_fields_set__", fields, raising=False)
    return fields


def test_good_settings_have_no_problems(secure):
    assert find_insecure_settings() == [] and check_startup_security() == []


@pytest.mark.parametrize(
    ("name", "value", "fragment"),
    [
        ("JWT_SECRET", "change_me", "JWT_SECRET"),
        ("JWT_SECRET", "generate_secure_secret_in_production", "JWT_SECRET"),
        ("JWT_SECRET", "too-short", "JWT_SECRET"),
        ("ADMIN_PASSWORD", "change_me_immediately", "ADMIN_PASSWORD"),
        ("ADMIN_PASSWORD", "weak-pw", "ADMIN_PASSWORD"),
        ("DATABASE_URL", "postgresql+asyncpg://si:change_me_in_production@postgres:5432/si", "database password"),
        ("DATABASE_URL", "postgresql+asyncpg://si@postgres:5432/si", "database password"),
        ("REDIS_URL", "redis://:change_me_too@redis:6379/0", "Redis password"),
        ("REDIS_PASSWORD", "change_me_too", "Redis password"),
    ],
)
def test_each_placeholder_or_weak_secret_is_reported(secure, monkeypatch, name, value, fragment):
    monkeypatch.setattr(settings, name, value)

    problems = find_insecure_settings()

    assert len(problems) == 1 and fragment in problems[0]
    assert value not in problems[0]  # the message names the setting, never its value


def test_a_jwt_secret_that_was_never_set_is_reported(secure, monkeypatch):
    monkeypatch.setattr(settings, "__pydantic_fields_set__", set(secure) - {"JWT_SECRET"}, raising=False)

    [problem] = find_insecure_settings()

    assert "JWT_SECRET is not set" in problem and "signs everyone out" in problem


def test_production_refuses_to_start_and_lists_every_problem(secure, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "change_me_immediately")
    monkeypatch.setattr(settings, "JWT_SECRET", "change_me")

    with pytest.raises(RuntimeError) as caught:
        check_startup_security()

    message = str(caught.value)
    assert "Refusing to start in production" in message and "ADMIN_PASSWORD" in message and "JWT_SECRET" in message
    assert "change_me" not in message.replace("placeholder", "")


@pytest.mark.parametrize("environment", ["development", "staging", "test"])
def test_other_environments_only_warn(secure, monkeypatch, environment):
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "change_me_immediately")
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(str(m)), level="WARNING")
    try:
        problems = check_startup_security()
    finally:
        logger.remove(sink)

    assert len(problems) == 1 and any("Insecure setting" in line and "ADMIN_PASSWORD" in line for line in lines)


def test_the_environment_name_is_case_insensitive(secure, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "Production")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "change_me_immediately")

    with pytest.raises(RuntimeError):
        check_startup_security()


def test_the_shipped_placeholders_are_all_known():
    for value in ("change_me_in_production", "change_me_too", "change_me_immediately",
                  "generate_secure_secret_in_production", "generate_a_secure_random_secret_here_minimum_32_chars"):
        assert value in startup_checks.PLACEHOLDER_SECRETS


# ---------------------------------------------------------------- new passwords


@pytest.mark.parametrize(
    ("new", "current", "expected"),
    [
        ("a-brand-new-passphrase", "old-password-1", None),
        ("short", "old-password-1", "at least 10 characters"),
        ("exactly-10", "old-password-1", None),
        ("123456789", "old-password-1", "at least 10 characters"),
        ("same-as-before-1", "same-as-before-1", "different from the current one"),
        ("change_me_immediately", "old-password-1", "well-known placeholder"),
        ("x" * 257, "old-password-1", "at most 256 characters"),
    ],
)
def test_password_policy(new, current, expected):
    result = check_new_password(new, current)

    assert (result is None) if expected is None else (expected in result)
    assert result is None or new not in result  # a message never echoes the password
