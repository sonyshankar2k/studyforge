"""Request-scoped dependencies (FastAPI's version of Angular DI)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.security import decode_access_token

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# tokenUrl powers the "Authorize" button in Swagger UI (/docs).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    """Resolve the Bearer token to a user, or reject the request with 401."""
    user_id = decode_access_token(token)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUserDep = Annotated[User, Depends(current_user)]


async def current_user_email(user: CurrentUserDep) -> str:
    """What the audit trail records as `changed_by` (attributable, per ALCOA+)."""
    return user.email


UserDep = Annotated[str, Depends(current_user_email)]
