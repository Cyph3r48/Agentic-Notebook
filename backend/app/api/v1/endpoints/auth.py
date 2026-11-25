"""Authentication endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.core.config import settings
from app.core.password_policy import check_new_password
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.throttle import login_throttle, password_throttle
from app.models import User
from app.repositories import SessionRepository, UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.services import audit


router = APIRouter(prefix="/auth")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> TokenResponse:
    request_id = getattr(request.state, "request_id", None)
    log = logger.bind(request_id=request_id, action="auth_login")
    log.info("Login attempt for email={email}", email=payload.email)

    users = UserRepository(session)
    sessions = SessionRepository(session)

    client = request.client.host if request.client else "unknown"
    throttle_key = f"{payload.email.lower()}|{client}"
    locked_for = login_throttle.locked_for(throttle_key)
    if locked_for:
        await audit.record(
            request, "auth_login_locked", details={"email": payload.email.lower(), "retry_after_seconds": locked_for},
            status_code=429, flagged=True, flag_reason="Sign-in refused: too many failed attempts",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_lock_message(locked_for),
            headers={"Retry-After": str(locked_for)},
        )

    user = await users.get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        log.warning("Login failed: invalid credentials for email={email}", email=payload.email)
        just_locked = login_throttle.record_failure(throttle_key)
        await audit.record(
            request, "auth_login_failed", user_id=user.id if user else None,
            details={"email": payload.email.lower(), "locked": just_locked}, status_code=401,
            flagged=just_locked, flag_reason="Account locked after repeated failed sign-ins" if just_locked else None,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        log.warning("Login blocked: disabled account user_id={user_id}", user_id=str(user.id))
        await audit.record(request, "auth_login_disabled", user_id=user.id, status_code=403)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    login_throttle.reset(throttle_key)

    token = create_access_token(
        subject=str(user.id),
        extra={"email": user.email, "role": user.role},
    )
    refresh_token, refresh_expires_at = create_refresh_token(subject=str(user.id))
    await sessions.create_session(
        user_id=user.id,
        session_token=refresh_token,
        expires_at=refresh_expires_at,
    )
    await users.set_last_login(user, datetime.now(tz=timezone.utc))
    log.info("Login succeeded user_id={user_id}", user_id=str(user.id))
    await audit.record(request, "auth_login", user_id=user.id, status_code=200)

    return TokenResponse(
        access_token=token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        role=current_user.role,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> TokenResponse:
    request_id = getattr(request.state, "request_id", None)
    log = logger.bind(request_id=request_id, action="auth_refresh")
    log.info("Refresh attempt")

    users = UserRepository(session)
    sessions = SessionRepository(session)

    try:
        claims = decode_access_token(payload.refresh_token)
    except ValueError:
        log.warning("Refresh failed: invalid token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if claims.get("type") != "refresh":
        log.warning("Refresh failed: invalid token type")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type")

    try:
        user_id = UUID(str(claims.get("sub")))
    except (TypeError, ValueError):
        log.warning("Refresh failed: invalid token subject")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token subject")

    token_row = await sessions.get_by_token_and_user(token=payload.refresh_token, user_id=user_id)
    if token_row is None:
        log.warning("Refresh failed: token not found user_id={user_id}", user_id=str(user_id))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not found")
    if token_row.expires_at <= datetime.now(tz=timezone.utc):
        await sessions.delete(token_row)
        log.warning("Refresh failed: token expired user_id={user_id}", user_id=str(user_id))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        log.warning("Refresh failed: user unavailable user_id={user_id}", user_id=str(user_id))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User unavailable")

    access_token = create_access_token(
        subject=str(user.id),
        extra={"email": user.email, "role": user.role},
    )
    new_refresh_token, new_expiry = create_refresh_token(subject=str(user.id))

    await sessions.rotate_session_token(token_row, token=new_refresh_token, expires_at=new_expiry)
    log.info("Refresh succeeded user_id={user_id}", user_id=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshTokenRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> None:
    request_id = getattr(request.state, "request_id", None)
    log = logger.bind(request_id=request_id, action="auth_logout")
    sessions = SessionRepository(session)
    await sessions.delete_by_token(payload.refresh_token)
    log.info("Logout completed")
    await audit.record(request, "auth_logout", status_code=204)


def _lock_message(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    return f"Too many failed attempts. Try again in about {minutes} minute{'s' if minutes != 1 else ''}."


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> TokenResponse:
    """Change your own password. Every other session is signed out; this device gets fresh tokens."""
    users = UserRepository(session)
    sessions = SessionRepository(session)
    key = f"pwchange:{current_user.id}"

    locked_for = password_throttle.locked_for(key)
    if locked_for:
        await audit.record(
            request, "password_change_locked", user_id=current_user.id, status_code=429,
            flagged=True, flag_reason="Password change refused: too many wrong current passwords",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_lock_message(locked_for),
            headers={"Retry-After": str(locked_for)},
        )

    if not verify_password(payload.current_password, current_user.password_hash):
        just_locked = password_throttle.record_failure(key)
        await audit.record(
            request, "password_change_failed", user_id=current_user.id, details={"locked": just_locked},
            status_code=400, flagged=just_locked,
            flag_reason="Password change locked after repeated wrong current passwords" if just_locked else None,
        )
        # 400, not 401: the web app treats 401 as "your session ended" and would sign the user out.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The current password is incorrect")
    password_throttle.reset(key)

    problem = check_new_password(payload.new_password, payload.current_password)
    if problem:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

    await users.set_password_hash(current_user, hash_password(payload.new_password))
    await sessions.delete_all_for_user(current_user.id)

    access_token = create_access_token(
        subject=str(current_user.id), extra={"email": current_user.email, "role": current_user.role}
    )
    refresh_token, refresh_expires_at = create_refresh_token(subject=str(current_user.id))
    await sessions.create_session(
        user_id=current_user.id, session_token=refresh_token, expires_at=refresh_expires_at
    )
    await audit.record(request, "password_changed", user_id=current_user.id, status_code=200)
    logger.bind(request_id=getattr(request.state, "request_id", None), action="auth_change_password").info(
        "Password changed user_id={user_id}", user_id=str(current_user.id)
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
