"""Report input and output contracts."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Title = Annotated[str, Field(min_length=3, max_length=120)]
Description = Annotated[str, Field(min_length=10, max_length=2000)]
Location = Annotated[str, Field(min_length=2, max_length=150)]
Reporter = Annotated[str, Field(min_length=2, max_length=100)]
Category = Literal["electronics", "clothing", "documents", "accessories", "other"]
ReportType = Literal["lost", "found"]
ReportStatus = Literal["open", "resolved"]
SortOrder = Literal["newest", "oldest"]


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def safe_text(cls, value):
        if isinstance(value, str) and (
            "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
        ):
            raise ValueError("Text contains an invalid Unicode or NUL character")
        return value


class ItemCreate(InputModel):
    title: Title
    description: Description
    category: Category
    location: Location
    type: ReportType


class ItemQuery(InputModel):
    archived: bool = False
    q: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    location: Annotated[str, Field(min_length=1, max_length=150)] | None = None
    category: Category | None = None
    type: ReportType | None = None
    status: ReportStatus | None = None
    sort: SortOrder = "newest"
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2**63 - 1)


class ItemUpdate(InputModel):
    title: Title | None = None
    description: Description | None = None
    category: Category | None = None
    location: Location | None = None
    type: ReportType | None = None
    status: ReportStatus | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "ItemUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Updated fields cannot be null")
        return self


class ItemRead(ItemCreate):
    model_config = ConfigDict(
        from_attributes=True, str_strip_whitespace=True, extra="forbid"
    )
    id: int
    archived: bool
    reported_by: Reporter
    reporter_id: int | None
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
