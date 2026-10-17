"""Add an audit event inside the caller's transaction."""

from datetime import datetime, timezone

from app.models.audit import AuditEvent


def audit(
    session, actor, action, item_id=None, claim_id=None, target_user_id=None, details=""
):
    session.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            actor_role=actor.role if actor else "local_admin",
            action=action,
            item_id=item_id,
            claim_id=claim_id,
            target_user_id=target_user_id,
            details=details,
            created_at=datetime.now(timezone.utc),
        )
    )
