"""Register every mapped table whenever the model package is imported."""

from app.models.account_tokens import AccountToken
from app.models.audit import AuditEvent
from app.models.claims import Claim
from app.models.items import Item
from app.models.media import ItemPhoto
from app.models.notifications import Notification
from app.models.users import User

__all__ = [
    "Item",
    "User",
    "Claim",
    "ItemPhoto",
    "Notification",
    "AccountToken",
    "AuditEvent",
]
