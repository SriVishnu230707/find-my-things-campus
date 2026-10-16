"""Serialize report workflows before checking or changing claim state."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.claims import Claim
from app.models.items import Item
from app.schemas.claims import ClaimRead
from app.services.notifications import notify, reviewers


def lock_item(session, item_id):
    # A write lock serializes SQLite workflows; UPDATE also locks the row on PostgreSQL.
    found = session.execute(
        update(Item).where(Item.id == item_id).values(id=Item.id).returning(Item.id)
    ).scalar_one_or_none()
    if found is None:
        raise HTTPException(404, "Item not found")
    return session.get(Item, item_id, populate_existing=True)


def moderator(item, user):
    if user.role != "staff" and item.reporter_id != user.id:
        raise HTTPException(403, "Report owner or staff required")


def has_claims(session, item_id, active=False):
    query = select(Claim.id).where(Claim.item_id == item_id)
    if active:
        query = query.where(Claim.status.in_(["pending", "approved"]))
    return session.scalar(query.limit(1)) is not None


def create_claim(session, item_id, user, evidence):
    item = lock_item(session, item_id)
    if user.role != "student":
        raise HTTPException(403, "Only students can submit claims")
    if item.reporter_id == user.id:
        raise HTTPException(403, "Cannot claim your own report")
    if item.archived or item.type != "found" or item.status != "open":
        raise HTTPException(409, "Claims require an open, unarchived found report")
    if session.scalar(
        select(Claim.id).where(
            Claim.item_id == item_id, Claim.status.in_(["approved", "completed"])
        )
    ):
        raise HTTPException(409, "Item already reserved or returned")
    now = datetime.now(timezone.utc)
    claim = Claim(
        item_id=item_id,
        claimant_id=user.id,
        evidence=evidence,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(claim)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "An active claim already exists") from None
    notify(
        session,
        reviewers(session, item),
        item.id,
        claim.id,
        "claim_submitted",
        f"A new claim (#{claim.id}) needs review on report #{item.id}.",
        user.id,
    )
    result = ClaimRead.model_validate(claim)
    session.commit()
    return result


def transition(session, claim_id, user, action):
    item_id = session.scalar(select(Claim.item_id).where(Claim.id == claim_id))
    if item_id is None:
        raise HTTPException(404, "Claim not found")
    item = lock_item(session, item_id)
    claim = session.get(Claim, claim_id, populate_existing=True)
    if action == "withdrawn":
        if claim.claimant_id != user.id:
            raise HTTPException(403, "Only the claimant can withdraw")
        allowed = ["pending", "approved"]
    else:
        moderator(item, user)
        if claim.claimant_id == user.id and user.role != "staff":
            raise HTTPException(403, "Cannot review your own claim")
        allowed = ["approved"] if action == "completed" else ["pending"]
    if item.archived or item.status != "open" or claim.status not in allowed:
        raise HTTPException(409, "Invalid claim transition")
    reviewer_ids = reviewers(session, item)
    if action == "approved" and session.scalar(
        select(Claim.id).where(
            Claim.item_id == item_id,
            Claim.id != claim_id,
            Claim.status.in_(["approved", "completed"]),
        )
    ):
        raise HTTPException(409, "Another claim already reserves this item")
    remaining = (
        list(
            session.scalars(
                select(Claim).where(
                    Claim.item_id == item_id,
                    Claim.id != claim_id,
                    Claim.status == "pending",
                )
            )
        )
        if action == "completed"
        else []
    )
    now = datetime.now(timezone.utc)
    claim.status = action
    claim.updated_at = now
    if action == "completed":
        item.status = "resolved"
        item.updated_at = now
        session.execute(
            update(Claim)
            .where(
                Claim.item_id == item_id,
                Claim.id != claim_id,
                Claim.status == "pending",
            )
            .values(status="rejected", updated_at=now)
        )
        for other in remaining:
            notify(
                session,
                {other.claimant_id},
                item_id,
                other.id,
                "claim_rejected",
                f"Claim #{other.id} was rejected because report #{item_id} was returned to another claimant.",
                user.id,
            )
    recipients = (
        reviewer_ids if action == "withdrawn" else reviewer_ids | {claim.claimant_id}
    )
    kind = "handover_completed" if action == "completed" else f"claim_{action}"
    message = (
        f"Handover completed for claim #{claim.id}; report #{item_id} is resolved."
        if action == "completed"
        else f"Claim #{claim.id} on report #{item_id} was {action}."
    )
    notify(session, recipients, item_id, claim.id, kind, message, user.id)
    session.flush()
    result = ClaimRead.model_validate(claim)
    session.commit()
    return result
