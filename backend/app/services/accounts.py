"""Purpose-bound, expiring, single-use email tokens with serialized consumption."""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update

from app.account_config import campus_address, campus_domains
from app.models.account_tokens import AccountToken
from app.models.users import User
from app.security import hash_password
from app.services.audit import audit
from app.services.mail import deliver_account_email

GENERIC_MESSAGE = (
    "If the account is eligible, instructions have been sent. Check your email."
)


def lock_user(session, user_id):
    found = session.scalar(
        update(User).where(User.id == user_id).values(id=User.id).returning(User.id)
    )
    return session.get(User, found, populate_existing=True) if found else None


def request_email(session, email, purpose):
    user_id = session.scalar(select(User.id).where(User.email == email))
    if user_id is None:
        return
    user = lock_user(session, user_id)
    if (
        not user
        or not user.is_active
        or (
            purpose == "verify"
            and (
                user.email_verified
                or (campus_domains() and not campus_address(user.email))
            )
        )
    ):
        return
    now = datetime.now(timezone.utc)
    recent = session.scalar(
        select(AccountToken.created_at)
        .where(AccountToken.user_id == user.id, AccountToken.purpose == purpose)
        .order_by(AccountToken.id.desc())
        .limit(1)
    )
    if recent and now - recent < timedelta(seconds=60):
        return
    session.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    token = secrets.token_urlsafe(32)
    session.add(
        AccountToken(
            user_id=user.id,
            purpose=purpose,
            digest=hashlib.sha256(token.encode()).hexdigest(),
            session_version=user.token_version,
            created_at=now,
            expires_at=now + timedelta(minutes=30 if purpose == "verify" else 15),
        )
    )
    session.flush()
    path = None
    try:
        path = deliver_account_email(user.email, purpose, token)
        session.commit()
    except Exception as error:
        session.rollback()
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning(
                    "Could not remove failed development email"
                )
        logging.getLogger(__name__).warning(
            "Account email delivery failed (%s)", type(error).__name__
        )
        # Same public response for unknown accounts and unavailable delivery.


def consume_token(session, raw, purpose, password=None):
    digest = hashlib.sha256(raw.encode()).hexdigest()
    token_user = session.scalar(
        select(AccountToken.user_id).where(
            AccountToken.digest == digest, AccountToken.purpose == purpose
        )
    )
    failure = HTTPException(400, "Link is invalid, expired, or already used")
    if token_user is None:
        raise failure
    user = lock_user(session, token_user)
    if user is None or not user.is_active:
        raise failure
    if purpose == "verify" and campus_domains() and not campus_address(user.email):
        raise failure
    now = datetime.now(timezone.utc)
    token_id = session.scalar(
        update(AccountToken)
        .where(
            AccountToken.digest == digest,
            AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None),
            AccountToken.expires_at > now,
            AccountToken.session_version == user.token_version,
        )
        .values(used_at=now)
        .returning(AccountToken.id)
    )
    if token_id is None:
        raise failure
    if purpose == "verify":
        user.email_verified = True
        audit(session, user, "email_verified", target_user_id=user.id)
    else:
        user.password_hash = hash_password(password)
        user.token_version += 1
        session.execute(
            update(AccountToken)
            .where(AccountToken.user_id == user.id, AccountToken.used_at.is_(None))
            .values(used_at=now)
        )
        audit(session, user, "password_reset", target_user_id=user.id)
    user.updated_at = now
    session.commit()
