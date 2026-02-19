"""
JWT auth with role claim (customer, manager). OAuth2PasswordBearer pattern.
Token payload includes: sub (user id), role, exp.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings
from app.core.security import verify_password
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=True)


class TokenPayload(BaseModel):
    sub: str  # user id
    role: str  # customer | manager
    exp: datetime


def create_access_token(user_id: UUID, role: UserRole) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": str(user_id), "role": role.value, "exp": expire}
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    from app.repositories.user_repo import UserRepository
    from app.db import AsyncSessionLocal

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        settings = get_settings()
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(UUID(sub))
    if user is None:
        raise credentials_exception
    return user


def require_role(*allowed: UserRole):
    """Dependency: require current user to have one of the allowed roles."""

    async def _require(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return Depends(_require)
