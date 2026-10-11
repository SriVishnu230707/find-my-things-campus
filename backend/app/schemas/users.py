"""Public account contracts with no password-hash fields."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.schemas.items import InputModel, Reporter


def normalize_email(value: str) -> str:
    # This application treats the entire address as case-insensitive.
    return value.strip().casefold()


class UserRegister(InputModel):
    # Passwords must be preserved exactly; trim only non-secret fields below.
    model_config = ConfigDict(str_strip_whitespace=False, extra="forbid")
    email: Annotated[EmailStr, Field(max_length=254)]
    display_name: Reporter
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_display_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email", mode="after")
    @classmethod
    def canonical_email(cls, value):
        return normalize_email(value)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    display_name: str
    role: Literal["student", "staff"]
    created_at: datetime
    updated_at: datetime


class TokenRead(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
