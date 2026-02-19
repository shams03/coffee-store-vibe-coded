from __future__ import annotations

from pydantic import BaseModel, EmailStr


class TokenRequest(BaseModel):
    """POST /api/v1/auth/token (form: username=email, password=...)."""

    username: EmailStr  # OAuth2 uses 'username' for email
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
