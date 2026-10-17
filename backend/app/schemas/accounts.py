"""Verification, recovery and staff contracts with redacted secret inputs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.schemas.items import InputModel


class EmailRequest(InputModel):
    email: EmailStr = Field(max_length=254)


class TokenConfirm(InputModel):
    token: SecretStr = Field(min_length=40, max_length=128)


class PasswordReset(TokenConfirm):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    password: SecretStr = Field(min_length=12, max_length=128)


class MessageRead(BaseModel):
    message: str


class AccountStatus(InputModel):
    is_active: bool
    reason: str = Field(min_length=8, max_length=500)


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: int | None
    actor_role: str
    action: str
    item_id: int | None
    claim_id: int | None
    target_user_id: int | None
    details: str
    created_at: datetime


class StaffSummary(BaseModel):
    users: int
    verified_users: int
    active_users: int
    reports: int
    open_reports: int
    resolved_reports: int
    archived_reports: int
    pending_claims: int
