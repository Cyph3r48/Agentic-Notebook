"""Authentication API schemas."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUserResponse(BaseModel):
    id: str
    email: EmailStr
    username: str
    full_name: str | None = None
    role: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str
