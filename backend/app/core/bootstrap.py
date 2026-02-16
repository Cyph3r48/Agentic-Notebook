"""Startup bootstrap routines."""

from sqlalchemy import select
from sqlalchemy import or_

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User


def _default_admin_username() -> str:
    local = settings.ADMIN_EMAIL.split("@")[0].strip().lower()
    return local or "admin"


async def ensure_admin_user() -> None:
    desired_username = _default_admin_username()
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(User).where(
                or_(
                    User.email == settings.ADMIN_EMAIL,
                    User.username == desired_username,
                )
            )
        )
        if existing is not None:
            updated = False
            if existing.email != settings.ADMIN_EMAIL:
                existing.email = settings.ADMIN_EMAIL
                updated = True
            if existing.username != desired_username:
                existing.username = desired_username
                updated = True
            if existing.full_name != settings.ADMIN_NAME:
                existing.full_name = settings.ADMIN_NAME
                updated = True
            if existing.role != "admin":
                existing.role = "admin"
                updated = True
            if not existing.is_active:
                existing.is_active = True
                updated = True
            if not existing.is_verified:
                existing.is_verified = True
                updated = True

            if updated or not existing.password_hash:
                existing.password_hash = hash_password(settings.ADMIN_PASSWORD)
                updated = True

            if updated:
                await session.commit()
            return

        admin = User(
            email=settings.ADMIN_EMAIL,
            username=desired_username,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            full_name=settings.ADMIN_NAME,
            role="admin",
            is_active=True,
            is_verified=True,
        )
        session.add(admin)
        await session.commit()
