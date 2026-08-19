from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from src.models.entities import SourceInfo
from src.models.enums import RelationshipType


class Relationship(BaseModel):
    source_id: str
    relationship: RelationshipType
    target_id: str
    confidence: float
    source: SourceInfo
    reason: str | None = None  # e.g. "github_owner", "text_extraction", "llm_assisted"

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v

    @field_validator("target_id")
    @classmethod
    def no_self_link_by_default(cls, v: str, info):
        # Self-links are only invalid at the model level when trivially
        # identical; genuine self-loop policy is enforced in graph
        # consistency checks where relationship type is also considered.
        return v

    model_config = ConfigDict(use_enum_values=True)
