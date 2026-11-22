"""Admin user management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, require_roles
from app.core.security import hash_password
from app.models import User
from app.repositories import UserRepository
from app.schemas.auth import CurrentUserResponse
from app.schemas.user import ProfileUpdateRequest, UserCreateRequest, UserResponse
from app.services import audit


router = APIRouter(prefix="/users")

ALLOWED_ROLES = {"admin", "user", "viewer"}


@router.patch("/me", response_model=CurrentUserResponse)
async def update_my_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> CurrentUserResponse:
    """Change your own display name. Email and username are fixed."""
    full_name = (payload.full_name or "").strip() or None
    if full_name and any(ord(ch) < 32 for ch in full_name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The name must not contain control characters")
    await UserRepository(session).set_full_name(current_user, full_name)
    await audit.record(request, "profile_updated", user_id=current_user.id, details={"fields": ["full_name"]}, status_code=200)
    return CurrentUserResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        role=current_user.role,
    )


@router.get("", response_model=list[UserResponse])
async def list_users(
    session: AsyncSession = Depends(db_session),
    _admin: User = Depends(require_roles("admin")),
) -> list[UserResponse]:
    users = await UserRepository(session).list_users()
    return [
        UserResponse(
            id=str(user.id),
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
        )
        for user in users
    ]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    _admin: User = Depends(require_roles("admin")),
) -> UserResponse:
    users = UserRepository(session)

    if payload.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    existing_email = await users.get_by_email(payload.email)
    if existing_email is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    existing_username = await users.get_by_username(payload.username)
    if existing_username is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = await users.create_user(
        email=payload.email,
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
        is_verified=True,
    )
    await audit.record(
        request, "user_created", user_id=_admin.id, resource_type="user", resource_id=user.id,
        details={"role": payload.role}, status_code=201,
    )

    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )
