"""Staff-only overview, review queues, account suspension and audit history."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import StaffUser
from app.database import get_session
from app.models.audit import AuditEvent
from app.models.claims import Claim
from app.models.items import Item
from app.models.users import User
from app.routers.items import ItemID
from app.schemas.accounts import AccountStatus, AuditRead, StaffSummary
from app.schemas.claims import ClaimRead
from app.schemas.items import ItemQuery, ItemRead
from app.schemas.users import UserRead
from app.services.accounts import lock_user
from app.services.audit import audit
from app.services.items import ItemRepository

router = APIRouter(prefix="/staff", tags=["Staff"])
DB = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=2**63 - 1)]


@router.get("/summary", response_model=StaffSummary)
def summary(user: StaffUser, session: DB):
    def count(model, *conditions):
        return session.scalar(
            select(func.count()).select_from(model).where(*conditions)
        )

    return {
        "users": count(User),
        "verified_users": count(User, User.email_verified.is_(True)),
        "active_users": count(User, User.is_active.is_(True)),
        "reports": count(Item),
        "open_reports": count(Item, Item.status == "open", Item.archived.is_(False)),
        "resolved_reports": count(
            Item, Item.status == "resolved", Item.archived.is_(False)
        ),
        "archived_reports": count(Item, Item.archived.is_(True)),
        "pending_claims": count(Claim, Claim.status == "pending"),
    }


@router.get("/reports", response_model=list[ItemRead])
def reports(user: StaffUser, session: DB, filters: Annotated[ItemQuery, Query()]):
    return ItemRepository(session).list(filters)


@router.get("/claims", response_model=list[ClaimRead])
def claims(
    user: StaffUser,
    session: DB,
    status: Literal[
        "pending", "approved", "rejected", "withdrawn", "completed"
    ] = "pending",
    limit: Limit = 20,
    offset: Offset = 0,
):
    return list(
        session.scalars(
            select(Claim)
            .where(Claim.status == status)
            .order_by(Claim.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/users", response_model=list[UserRead])
def users(user: StaffUser, session: DB, limit: Limit = 20, offset: Offset = 0):
    return list(
        session.scalars(
            select(User).order_by(User.id.desc()).limit(limit).offset(offset)
        )
    )


@router.patch("/users/{user_id}/status", response_model=UserRead)
def set_status(user_id: ItemID, data: AccountStatus, actor: StaffUser, session: DB):
    # Serialize account changes and recheck staff authority after acquiring the lock.
    current_actor = lock_user(session, actor.id)
    if (
        not current_actor
        or not current_actor.is_active
        or current_actor.role != "staff"
    ):
        raise HTTPException(403, "Staff access required")
    target = lock_user(session, user_id)
    if target is None:
        raise HTTPException(404, "Account not found")
    if target.role == "staff":
        raise HTTPException(409, "Staff accounts must be administered locally")
    if target.is_active != data.is_active:
        target.is_active = data.is_active
        target.token_version += 1
        target.updated_at = datetime.now(timezone.utc)
        audit(
            session,
            current_actor,
            "account_enabled" if data.is_active else "account_disabled",
            target_user_id=target.id,
            details=data.reason,
        )
    result = UserRead.model_validate(target)
    session.commit()
    return result


@router.get("/audit", response_model=list[AuditRead])
def audit_history(user: StaffUser, session: DB, limit: Limit = 20, offset: Offset = 0):
    return list(
        session.scalars(
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
