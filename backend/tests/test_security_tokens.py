from __future__ import annotations

from app.core.security import create_access_token, create_refresh_token


def test_access_tokens_include_unique_jti():
    first = create_access_token(subject="user-1")
    second = create_access_token(subject="user-1")
    assert first != second


def test_refresh_tokens_include_unique_jti():
    first, _ = create_refresh_token(subject="user-1")
    second, _ = create_refresh_token(subject="user-1")
    assert first != second
