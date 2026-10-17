"""Registration, OAuth2 form login, and current user profile."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.account_config import (
    campus_address,
    campus_domains,
    mail_mode,
    verification_required,
)
from app.auth import CurrentUser
from app.auth_limits import auth_guard
from app.database import get_session
from app.models.users import User
from app.schemas.accounts import EmailRequest, MessageRead, PasswordReset, TokenConfirm
from app.schemas.users import TokenRead, UserRead, UserRegister, normalize_email
from app.security import (
    TOKEN_SECONDS,
    create_token,
    dummy_hash,
    hash_password,
    verify_password,
)
from app.services.accounts import GENERIC_MESSAGE, consume_token, request_email

router = APIRouter(prefix="/auth", tags=["Accounts"])
DB = Annotated[Session, Depends(get_session)]


@router.post(
    "/register",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(auth_guard)],
)
def register(data: UserRegister, session: DB):
    if campus_domains() and not campus_address(str(data.email)):
        raise HTTPException(422, "Use an approved campus email domain")
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
    if user is None or not valid or not user.is_active:
        raise failure
    return TokenRead(
        access_token=create_token(user.id, user.token_version), expires_in=TOKEN_SECONDS
    )


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser):
    return UserRead.model_validate(user)


@router.get("/config")
def config():
    return {
        "verification_required": verification_required(),
        "campus_domains": list(campus_domains()),
        "email_delivery": mail_mode(),
    }


@router.post(
    "/verification/request",
    response_model=MessageRead,
    status_code=202,
    dependencies=[Depends(auth_guard)],
)
def request_verification(data: EmailRequest, session: DB):
    request_email(session, normalize_email(str(data.email)), "verify")
    return {"message": GENERIC_MESSAGE}


@router.post(
    "/verification/confirm",
    response_model=MessageRead,
    dependencies=[Depends(auth_guard)],
)
def confirm_verification(data: TokenConfirm, session: DB):
    consume_token(session, data.token.get_secret_value(), "verify")
    return {"message": "Email verified. You may now use eligible campus features."}


@router.post(
    "/password/request",
    response_model=MessageRead,
    status_code=202,
    dependencies=[Depends(auth_guard)],
)
def request_password(data: EmailRequest, session: DB):
    request_email(session, normalize_email(str(data.email)), "reset")
    return {"message": GENERIC_MESSAGE}


@router.post(
    "/password/reset", response_model=MessageRead, dependencies=[Depends(auth_guard)]
)
def reset_password(data: PasswordReset, session: DB):
    consume_token(
        session,
        data.token.get_secret_value(),
        "reset",
        data.password.get_secret_value(),
    )
    return {
        "message": "Password updated. Sign in again; previous sessions have been revoked."
    }
