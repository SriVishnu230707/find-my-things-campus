"""Private claim contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.items import InputModel


class ClaimCreate(InputModel):
    evidence: str = Field(min_length=10, max_length=2000)


class ClaimDecision(InputModel):
    decision: Literal["approved", "rejected"]


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int
    claimant_id: int
    evidence: str
    status: Literal["pending", "approved", "rejected", "withdrawn", "completed"]
    created_at: datetime
    updated_at: datetime
