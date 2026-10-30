"""Sign-up, sign-in and "who am I"."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.deps import CurrentUserDep, SessionDep
from app.models import User
from app.schemas import RegisterRequest, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _normalize(email: str) -> str:
    return email.strip().lower()


async def _find_user(session, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == _normalize(email))
    return (await session.execute(stmt)).scalar_one_or_none()


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: SessionDep):
    if await _find_user(session, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=_normalize(body.email),
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
    )
    session.add(user)
    await session.commit()
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep):
    """OAuth2 password flow: form fields `username` (the email) and `password`."""
    user = await _find_user(session, form.username)
    # Same error for "no such user" and "wrong password", so attackers
    # can't use this endpoint to discover which emails are registered.
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserDep):
    return user
