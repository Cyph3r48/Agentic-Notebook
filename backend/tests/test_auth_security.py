from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app import main as main_module
from app.api.deps import db_session, get_current_user
from app.api.v1.endpoints import auth as auth_module
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.users import router as users_router
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.core.throttle import FailureThrottle

PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "a-brand-new-passphrase"
PASSWORD_HASH = hash_password(PASSWORD)  # hashing is slow on purpose; do it once for the whole file


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


async def _fake_db_session():
    yield object()


class _Users:
    def __init__(self, user):
        self.user = user
        self.password_hashes: list[str] = []
        self.names: list = []

    async def get_by_email(self, email):
        return self.user if self.user and self.user.email == email else None

    async def set_last_login(self, user, value):
        user.last_login = value

    async def set_password_hash(self, user, password_hash):
        user.password_hash = password_hash
        self.password_hashes.append(password_hash)

    async def set_full_name(self, user, full_name):
        user.full_name = full_name
        self.names.append(full_name)


class _Sessions:
    def __init__(self):
        self.created: list[dict] = []
        self.deleted_for: list = []

    async def create_session(self, **kwargs):
        self.created.append(kwargs)

    async def delete_all_for_user(self, user_id):
        self.deleted_for.append(user_id)

    async def delete_by_token(self, token):
        pass


@pytest.fixture
def world(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(), email="user@example.com", username="user", full_name="Old Name", role="user",
        is_active=True, password_hash=PASSWORD_HASH, last_login=None,
    )
    users, sessions, clock = _Users(user), _Sessions(), _Clock()
    monkeypatch.setattr(auth_module, "UserRepository", lambda _session: users)
    monkeypatch.setattr(auth_module, "SessionRepository", lambda _session: sessions)
    monkeypatch.setattr(auth_module, "login_throttle", FailureThrottle(clock))
    monkeypatch.setattr(auth_module, "password_throttle", FailureThrottle(clock))
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 5)
    monkeypatch.setattr(settings, "LOGIN_LOCK_SECONDS", 900)
    # the users router imports its own repository name
    from app.api.v1.endpoints import users as users_module

    monkeypatch.setattr(users_module, "UserRepository", lambda _session: users)
    return SimpleNamespace(user=user, users=users, sessions=sessions, clock=clock)


def _client(world, *, signed_in=True):
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, main_module.validation_error_handler)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.dependency_overrides[db_session] = _fake_db_session
    if signed_in:
        app.dependency_overrides[get_current_user] = lambda: world.user
    return TestClient(app)


def _login(client, password=PASSWORD, email="user@example.com"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _actions(events, name):
    return [e for e in events if e["action"] == name]


# ---------------------------------------------------------------- the throttle itself


def test_a_key_locks_after_the_configured_number_of_failures_and_frees_after_the_window(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 3)
    monkeypatch.setattr(settings, "LOGIN_LOCK_SECONDS", 60)
    clock = _Clock()
    throttle = FailureThrottle(clock)

    assert [throttle.record_failure("k") for _ in range(3)] == [False, False, True]
    assert 0 < throttle.locked_for("k") <= 61
    clock.now += 61
    assert throttle.locked_for("k") == 0
    assert throttle.record_failure("k") is False  # a fresh count after the lock ends


def test_failures_older_than_the_window_do_not_add_up(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 3)
    monkeypatch.setattr(settings, "LOGIN_LOCK_SECONDS", 60)
    clock = _Clock()
    throttle = FailureThrottle(clock)

    throttle.record_failure("k")
    throttle.record_failure("k")
    clock.now += 120
    assert throttle.record_failure("k") is False and throttle.locked_for("k") == 0


def test_reset_and_separate_keys(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES", 2)
    throttle = FailureThrottle(_Clock())
    throttle.record_failure("a")
    throttle.record_failure("b")
    throttle.reset("a")

    assert throttle.record_failure("a") is False  # the reset cleared its count
    assert throttle.record_failure("b") is True and throttle.locked_for("b") and not throttle.locked_for("a")


# ---------------------------------------------------------------- login


def test_five_wrong_passwords_lock_the_account_key_and_even_the_right_password_waits(world, audit_events):
    with _client(world) as client:
        statuses = [_login(client, "wrong-password-1").status_code for _ in range(5)]
        locked = _login(client, PASSWORD)  # the right one, but the key is locked
        other = _login(client, "wrong-password-1", email="someone@example.com")

    assert statuses == [401, 401, 401, 401, 401]
    assert locked.status_code == 429 and "Try again in about 15 minutes" in locked.json()["detail"]
    assert int(locked.headers["retry-after"]) > 800
    assert other.status_code == 401  # another email is unaffected
    failures = _actions(audit_events, "auth_login_failed")
    assert [f["flagged"] for f in failures[:5]] == [False, False, False, False, True]
    [refused] = _actions(audit_events, "auth_login_locked")
    assert refused["flagged"] is True and refused["response_status"] == 429


def test_the_lock_ends_after_the_window_and_a_correct_login_works_again(world, audit_events):
    with _client(world) as client:
        for _ in range(5):
            _login(client, "wrong-password-1")
        assert _login(client, PASSWORD).status_code == 429
        world.clock.now += 901
        response = _login(client, PASSWORD)

    assert response.status_code == 200 and "access_token" in response.json()


def test_a_success_clears_earlier_failures(world, audit_events):
    with _client(world) as client:
        for _ in range(4):
            _login(client, "wrong-password-1")
        assert _login(client, PASSWORD).status_code == 200
        later = [_login(client, "wrong-password-1").status_code for _ in range(4)]

    assert later == [401, 401, 401, 401]  # four more failures after the reset still do not lock


def test_every_login_outcome_is_audited_and_no_password_ever_is(world, audit_events):
    with _client(world) as client:
        _login(client, "wrong-password-1")
        _login(client, "wrong-password-1", email="nobody@example.com")
        _login(client, PASSWORD)

    assert [e["action"] for e in audit_events] == ["auth_login_failed", "auth_login_failed", "auth_login"]
    known, unknown, ok = audit_events
    assert known["user_id"] == world.user.id and unknown["user_id"] is None and ok["user_id"] == world.user.id
    assert unknown["request_body"]["email"] == "nobody@example.com"
    assert "wrong-password" not in str(audit_events) and PASSWORD not in str(audit_events)


def test_a_disabled_account_is_audited(world, audit_events):
    world.user.is_active = False

    with _client(world) as client:
        response = _login(client)

    assert response.status_code == 403 and _actions(audit_events, "auth_login_disabled")


# ---------------------------------------------------------------- change password


def _change(client, current=PASSWORD, new=NEW_PASSWORD):
    return client.post("/api/v1/auth/change-password", json={"current_password": current, "new_password": new})


def test_changing_the_password_saves_a_hash_signs_out_other_sessions_and_returns_fresh_tokens(world, audit_events):
    with _client(world) as client:
        response = _change(client)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert world.sessions.deleted_for == [world.user.id]  # every old refresh token stops working
    assert len(world.sessions.created) == 1 and world.sessions.created[0]["session_token"] == body["refresh_token"]
    saved = world.users.password_hashes[0]
    assert saved != NEW_PASSWORD and verify_password(NEW_PASSWORD, saved) and not verify_password(PASSWORD, saved)
    [event] = _actions(audit_events, "password_changed")
    assert event["user_id"] == world.user.id
    assert NEW_PASSWORD not in str(audit_events) and PASSWORD not in str(audit_events)


def test_a_wrong_current_password_is_a_400_not_a_401_and_changes_nothing(world, audit_events):
    with _client(world) as client:
        response = _change(client, current="not-my-password")

    assert response.status_code == 400  # 401 would make the web app think the session ended
    assert "current password is incorrect" in response.json()["detail"]
    assert world.users.password_hashes == [] and world.sessions.deleted_for == []
    assert _actions(audit_events, "password_change_failed")


def test_repeated_wrong_current_passwords_lock_further_attempts(world, audit_events):
    with _client(world) as client:
        statuses = [_change(client, current="not-my-password").status_code for _ in range(5)]
        locked = _change(client)  # the right current password, but locked

    assert statuses == [400] * 5 and locked.status_code == 429
    assert world.users.password_hashes == []
    assert _actions(audit_events, "password_change_locked")[0]["flagged"] is True


@pytest.mark.parametrize(
    ("new", "message"),
    [
        ("short", "at least 10 characters"),
        (PASSWORD, "different from the current one"),
        ("change_me_immediately", "well-known placeholder"),
    ],
)
def test_weak_or_unchanged_new_passwords_are_refused(world, new, message):
    with _client(world) as client:
        response = _change(client, new=new)

    assert response.status_code == 400 and message in response.json()["detail"]
    assert world.users.password_hashes == []


def test_changing_a_password_requires_a_signed_in_user(world):
    with _client(world, signed_in=False) as client:
        assert _change(client).status_code == 401


def test_oversized_passwords_are_rejected_without_echoing_them(world):
    with _client(world) as client:
        response = _change(client, new="x" * 300)

    assert response.status_code == 422 and "xxxxxxxxxx" not in response.text


# ---------------------------------------------------------------- profile


def _patch(client, body):
    return client.patch("/api/v1/users/me", json=body)


def test_a_user_can_change_their_display_name_and_nothing_else(world, audit_events):
    with _client(world) as client:
        response = _patch(client, {"full_name": "  New Name  ", "email": "evil@example.com", "role": "admin", "username": "x"})

    assert response.status_code == 200 and response.json()["full_name"] == "New Name"
    assert (world.user.email, world.user.role, world.user.username) == ("user@example.com", "user", "user")
    assert _actions(audit_events, "profile_updated")[0]["request_body"] == {"fields": ["full_name"]}
    assert "New Name" not in str(audit_events)


def test_an_empty_name_clears_it(world):
    with _client(world) as client:
        assert _patch(client, {"full_name": "   "}).json()["full_name"] is None
        assert _patch(client, {"full_name": None}).json()["full_name"] is None


def test_names_with_control_characters_or_too_long_are_refused(world):
    with _client(world) as client:
        assert _patch(client, {"full_name": "bad\x00name"}).status_code == 400
        assert _patch(client, {"full_name": "n" * 256}).status_code == 422
    assert world.users.names == []


def test_the_profile_endpoint_needs_a_signed_in_user(world):
    with _client(world, signed_in=False) as client:
        assert _patch(client, {"full_name": "x"}).status_code == 401


def test_changed_tokens_expire_as_configured(world):
    with _client(world) as client:
        response = _change(client)

    assert response.json()["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
