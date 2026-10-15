from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    totp_code: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: Literal["owner", "admin", "user"]
    has_extension_access: bool


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime
    user: UserResponse
