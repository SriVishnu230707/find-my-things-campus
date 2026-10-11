"""Authentication dependency shared by protected routes."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.users import User
from app.security import decode_token

oauth2 = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    failure = HTTPException(
        401, "Invalid or expired authentication", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        user_id = decode_token(token)
    except jwt.InvalidTokenError:
        raise failure from None
    user = session.get(User, user_id)
    if user is None:
        raise failure
    # Role is read from the database on every request, never trusted from JWT claims.
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
