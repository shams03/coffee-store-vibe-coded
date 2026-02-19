"""
POST /api/v1/auth/token — login, returns JWT with role claim.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.core.security import verify_password
from app.db import get_db
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Login",
    description="Returns JWT access token. Token payload includes sub (user id), role (customer|manager), exp.",
)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    repo = UserRepository(session)
    user = await repo.get_by_email(form.username)
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, token_type="bearer")
