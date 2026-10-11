"""Registration, OAuth2 form login, and current user profile."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.auth_limits import auth_guard
from app.database import get_session
from app.models.users import User
from app.schemas.users import TokenRead, UserRead, UserRegister, normalize_email
from app.security import (
    TOKEN_SECONDS,
    create_token,
    dummy_hash,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Accounts"])
DB = Annotated[Session, Depends(get_session)]


@router.post(
    "/register",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(auth_guard)],
)
def register(data: UserRegister, session: DB):
    if session.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise HTTPException(409, "Email already registered")
    now = datetime.now(timezone.utc)
    user = User(
        email=str(data.email),
        display_name=data.display_name,
        password_hash=hash_password(data.password.get_secret_value()),
        role="student",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Email already registered") from None
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenRead, dependencies=[Depends(auth_guard)])
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: DB):
    # Bound input before expensive hashing; preserve passwords exactly.
    failure = HTTPException(
        401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"}
    )
    if len(form.username) > 254 or not 1 <= len(form.password) <= 128:
        raise failure
    user = session.scalar(
        select(User).where(User.email == normalize_email(form.username))
    )
    encoded = user.password_hash if user else dummy_hash()
    valid = verify_password(encoded, form.password)
    if user is None or not valid:
        raise failure
    return TokenRead(access_token=create_token(user.id), expires_in=TOKEN_SECONDS)


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser):
    return UserRead.model_validate(user)
