"""Register every mapped table whenever the model package is imported."""

from app.models.claims import Claim
from app.models.items import Item
from app.models.media import ItemPhoto
from app.models.notifications import Notification
from app.models.users import User

__all__ = ["Item", "User", "Claim", "ItemPhoto", "Notification"]
