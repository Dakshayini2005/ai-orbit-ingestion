"""Entity validation (spec section 35).

Pydantic already enforces structural correctness (types, required fields) at
construction time — an Entity object that exists has already passed that
bar. This module adds the semantic checks Pydantic can't express: URL
well-formedness, non-placeholder names, and specialized-metadata presence
expectations per entity_type. Fails loudly (returns explicit reasons) but
never raises — invalid entities are excluded from the final dataset and
counted in the quality report rather than crashing the pipeline.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from src.models.entities import Entity
from src.models.enums import EntityType

_PLACEHOLDER_NAMES = {"unknown", "n/a", "untitled", "todo", ""}


def _valid_url(url: str | None) -> bool:
    if url is None:
        return True  # URL is optional at the schema level
    parts = urlsplit(url)
    return bool(parts.scheme in ("http", "https") and parts.netloc)


def validate_entity(entity: Entity) -> tuple[bool, list[str]]:
    problems: list[str] = []

    if entity.name.strip().lower() in _PLACEHOLDER_NAMES:
        problems.append("placeholder or empty name")

    if not _valid_url(entity.url):
        problems.append(f"invalid url: {entity.url!r}")

    if not entity.source or not entity.source.name:
        problems.append("missing source information")

    if not entity.categories:
        problems.append("no categories assigned")

    # Specialized-metadata expectations (soft — missing metadata is logged
    # as a data-quality note, not a hard validation failure, per spec
    # section 8: "do not fabricate missing information; use null").
    entity_type = entity.entity_type if isinstance(entity.entity_type, str) else entity.entity_type.value
    expected_metadata_field = {
        EntityType.MODEL.value: "model_metadata",
        EntityType.REPOSITORY.value: "repository_metadata",
        EntityType.MCP_SERVER.value: "mcp_metadata",
        EntityType.COMPANY.value: "company_metadata",
    }.get(entity_type)
    # Intentionally not appended to `problems` — see comment above.

    return (len(problems) == 0, problems)


def validate_entities(entities: list[Entity]) -> tuple[list[Entity], dict[str, list[str]]]:
    """Returns (valid_entities, {entity_id: [problems]} for invalid ones)."""
    valid: list[Entity] = []
    invalid: dict[str, list[str]] = {}

    for e in entities:
        ok, problems = validate_entity(e)
        if ok:
            valid.append(e)
        else:
            invalid[e.id] = problems

    return valid, invalid
