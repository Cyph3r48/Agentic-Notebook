"""User management schemas."""

from pydantic import BaseModel, EmailStr, Field


class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=256)
    full_name: str | None = Field(default=None, max_length=255)
    role: str = Field(default="user")


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    username: str
    full_name: str | None = None
    role: str
    is_active: bool
    is_verified: bool
