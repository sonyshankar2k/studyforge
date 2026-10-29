"""Request-scoped dependencies (FastAPI's version of Angular DI)."""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_user(x_user: Annotated[str | None, Header()] = None) -> str:
    """Who is making the change.

    Starter version: trusts an `X-User` header so you can test multi-user
    editing in two browser tabs. Week 1 task: replace with JWT auth
    (OAuth2PasswordBearer + python-jose / PyJWT).
    """
    return (x_user or "anonymous").strip()[:100] or "anonymous"


UserDep = Annotated[str, Depends(current_user)]
