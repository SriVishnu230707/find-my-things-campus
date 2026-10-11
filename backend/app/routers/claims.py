"""Authenticated private claim submission and review."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.database import get_session
from app.models.claims import Claim
from app.models.items import Item
from app.routers.items import ItemID
from app.schemas.claims import ClaimCreate, ClaimDecision, ClaimRead
from app.services.claims import create_claim, moderator, transition

router = APIRouter(tags=["Claims"])
DB = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=2**63 - 1)]


@router.post("/items/{item_id}/claims", response_model=ClaimRead, status_code=201)
def submit(item_id: ItemID, data: ClaimCreate, user: CurrentUser, session: DB):
    return create_claim(session, item_id, user, data.evidence)


@router.get("/claims/me", response_model=list[ClaimRead])
def mine(user: CurrentUser, session: DB, limit: Limit = 100, offset: Offset = 0):
    return list(
        session.scalars(
            select(Claim)
            .where(Claim.claimant_id == user.id)
            .order_by(Claim.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/items/{item_id}/claims", response_model=list[ClaimRead])
def review(
    item_id: ItemID,
    user: CurrentUser,
    session: DB,
    limit: Limit = 100,
    offset: Offset = 0,
):
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    moderator(item, user)
    return list(
        session.scalars(
            select(Claim)
            .where(Claim.item_id == item_id)
            .order_by(Claim.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.patch("/claims/{claim_id}/decision", response_model=ClaimRead)
def decide(claim_id: ItemID, data: ClaimDecision, user: CurrentUser, session: DB):
    return transition(session, claim_id, user, data.decision)


@router.post("/claims/{claim_id}/withdraw", response_model=ClaimRead)
def withdraw(claim_id: ItemID, user: CurrentUser, session: DB):
    return transition(session, claim_id, user, "withdrawn")


@router.post("/claims/{claim_id}/handover", response_model=ClaimRead)
def handover(claim_id: ItemID, user: CurrentUser, session: DB):
    return transition(session, claim_id, user, "completed")
