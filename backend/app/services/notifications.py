"""Enqueue notifications inside the claim transaction, never commit separately."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.notifications import Notification
from app.models.users import User


def reviewers(session, item):
    if item.reporter_id is not None:
        return {item.reporter_id}
    return set(session.scalars(select(User.id).where(User.role == "staff")))


def notify(session, recipients, item_id, claim_id, kind, message, actor_id=None):
    for recipient in set(recipients) - {None, actor_id}:
        session.add(
            Notification(
                recipient_id=recipient,
                item_id=item_id,
                claim_id=claim_id,
                kind=kind,
                message=message,
                created_at=datetime.now(timezone.utc),
            )
        )
