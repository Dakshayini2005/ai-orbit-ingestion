"""Canonical entity schema plus specialized per-type metadata.

Design notes
------------
- IDs are DETERMINISTIC (uuid5 over entity_type + canonical URL, falling back
  to entity_type + normalized name when no URL exists). Re-running the
  pipeline on the same source data always produces the same entity IDs, which
  is what makes `--resume` and relationship references stable across runs.
- Specialized metadata (ModelMetadata, RepositoryMetadata, ...) is optional
  and lives in a single `metadata` field on the entity rather than as
  subclasses, so a mixed-type collection (List[Entity]) serializes to one
  flat, easy-to-consume entities.json instead of a tagged union.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.enums import EntityType, SourceName

# Fixed namespace so uuid5 output is stable across machines/runs.
_ID_NAMESPACE = uuid.UUID("6f2b3c9e-2b41-4a7a-9b7a-0d1a9b6e0a11")


def make_entity_id(entity_type: EntityType, canonical_key: str) -> str:
    """Deterministic ID: same (type, canonical URL/name) -> same ID, always."""
    seed = f"{entity_type.value}:{canonical_key.strip().lower()}"
    return str(uuid.uuid5(_ID_NAMESPACE, seed))


class SourceInfo(BaseModel):
    name: str
    url: Optional[str] = None


class ModelMetadata(BaseModel):
    license: Optional[str] = None
    modalities: list[str] = Field(default_factory=list)
    provider: Optional[str] = None
    downloads: Optional[int] = None
    pipeline_tag: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class RepositoryMetadata(BaseModel):
    stars: Optional[int] = None
    forks: Optional[int] = None
    primary_language: Optional[str] = None
    last_updated: Optional[str] = None
    created_at: Optional[str] = None
    license: Optional[str] = None
    topics: list[str] = Field(default_factory=list)
    owner: Optional[str] = None


class MCPServerMetadata(BaseModel):
    installation_methods: list[str] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(default_factory=list)


class CompanyMetadata(BaseModel):
    founding_year: Optional[int] = None
    industry_sector: Optional[str] = None
    headquarters: Optional[str] = None


class VideoMetadata(BaseModel):
    channel: Optional[str] = None
    video_id: Optional[str] = None
    published_date: Optional[str] = None


class NewsMetadata(BaseModel):
    publisher: Optional[str] = None
    published_date: Optional[str] = None


class Entity(BaseModel):
    id: str
    entity_type: EntityType
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    source: SourceInfo

    # Provenance / audit fields (not in the "minimal" schema from the spec,
    # but required for entity resolution, enrichment provenance, and the
    # quality report to be meaningful rather than decorative).
    aliases: list[str] = Field(default_factory=list)
    raw_names: list[str] = Field(default_factory=list)
    matched_source_records: int = 1
    first_seen: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Specialized metadata — only the field relevant to entity_type is set.
    model_metadata: Optional[ModelMetadata] = None
    repository_metadata: Optional[RepositoryMetadata] = None
    mcp_metadata: Optional[MCPServerMetadata] = None
    company_metadata: Optional[CompanyMetadata] = None
    video_metadata: Optional[VideoMetadata] = None
    news_metadata: Optional[NewsMetadata] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("entity name must not be blank")
        return v.strip()

    model_config = ConfigDict(use_enum_values=True)
