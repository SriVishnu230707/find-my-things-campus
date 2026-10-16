"""Notification responses expose only the current recipient's events."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int
    claim_id: int
    kind: str
    message: str
    is_read: bool
    created_at: datetime


class UnreadCount(BaseModel):
    unread_count: int


class ReadAllResult(BaseModel):
    updated: int
