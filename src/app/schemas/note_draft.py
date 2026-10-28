"""Single-call visual facts plus an editable draft that follows user intent."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.fast_note import VisualFactsBatch


class CreativeNoteDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    # Resource caps protect parsing/memory; publication targets are review hints.
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    tags: list[Annotated[str, StringConstraints(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=16)


class IntentAwareGeneration(VisualFactsBatch):
    user_context_used: list[Annotated[str, StringConstraints(min_length=1, max_length=300)]] = Field(default_factory=list, max_length=12)
    draft: CreativeNoteDraft
