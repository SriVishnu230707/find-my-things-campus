"""Report input and output contracts."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Title = Annotated[str, Field(min_length=3, max_length=120)]
Description = Annotated[str, Field(min_length=10, max_length=2000)]
Location = Annotated[str, Field(min_length=2, max_length=150)]
Reporter = Annotated[str, Field(min_length=2, max_length=100)]
Category = Literal["electronics", "clothing", "documents", "accessories", "other"]
ReportType = Literal["lost", "found"]
ReportStatus = Literal["open", "resolved"]


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ItemCreate(InputModel):
    title: Title
    description: Description
    category: Category
    location: Location
    type: ReportType
    reported_by: Reporter


class ItemUpdate(InputModel):
    title: Title | None = None
    description: Description | None = None
    category: Category | None = None
    location: Location | None = None
    type: ReportType | None = None
    reported_by: Reporter | None = None
    status: ReportStatus | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "ItemUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Updated fields cannot be null")
        return self


class ItemRead(ItemCreate):
    id: int
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
