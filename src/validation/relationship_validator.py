"""Relationship validation (spec sections 25-26).

Checked before a relationship is accepted:
  - source entity exists
  - target entity exists
  - relationship type is one of the allowed enum values (guaranteed by
    Pydantic construction, re-checked here defensively)
  - source/target entity types are compatible with the relationship type
  - confidence is in [0, 1] (guaranteed by Pydantic, re-checked defensively)
  - provenance (source info) exists
  - no self-links (source_id == target_id) unless the relationship type
    explicitly allows them (none currently do)
"""
from __future__ import annotations

from src.models.entities import Entity
from src.models.enums import RelationshipType, VALID_RELATIONSHIP_TYPE_PAIRS
from src.models.relationships import Relationship

_SELF_LINK_ALLOWED: set[RelationshipType] = set()  # none, currently


def validate_relationship(rel: Relationship, entity_by_id: dict[str, Entity]) -> tuple[bool, str]:
    source_entity = entity_by_id.get(rel.source_id)
    target_entity = entity_by_id.get(rel.target_id)

    if source_entity is None:
        return False, f"dangling source_id: {rel.source_id}"
    if target_entity is None:
        return False, f"dangling target_id: {rel.target_id}"

    if rel.source_id == rel.target_id:
        rel_type = rel.relationship if isinstance(rel.relationship, RelationshipType) else RelationshipType(rel.relationship)
        if rel_type not in _SELF_LINK_ALLOWED:
            return False, "self-link not permitted for this relationship type"

    if not (0.0 <= rel.confidence <= 1.0):
        return False, f"confidence out of range: {rel.confidence}"

    if not rel.source or not rel.source.name:
        return False, "missing relationship provenance"

    rel_type = rel.relationship if isinstance(rel.relationship, RelationshipType) else RelationshipType(rel.relationship)
    source_type = source_entity.entity_type if isinstance(source_entity.entity_type, str) else source_entity.entity_type.value
    target_type = target_entity.entity_type if isinstance(target_entity.entity_type, str) else target_entity.entity_type.value

    from src.models.enums import EntityType
    pair = (EntityType(source_type), EntityType(target_type))
    allowed_pairs = VALID_RELATIONSHIP_TYPE_PAIRS.get(rel_type, set())
    if pair not in allowed_pairs:
        return False, f"incompatible entity types for {rel_type.value}: {source_type} -> {target_type}"

    return True, ""


def validate_relationship_graph(relationships: list[Relationship]) -> tuple[list[Relationship], list[str]]:
    """Graph-level consistency check (spec section 26): removes exact
    duplicate relationships (same source/type/target). Individual-edge
    checks already ran in validate_relationship before this point.
    """
    seen: set[tuple[str, str, str]] = set()
    deduped: list[Relationship] = []
    notes: list[str] = []

    for rel in relationships:
        rel_type = rel.relationship if isinstance(rel.relationship, str) else rel.relationship.value
        key = (rel.source_id, rel_type, rel.target_id)
        if key in seen:
            notes.append(f"duplicate relationship removed: {key}")
            continue
        seen.add(key)
        deduped.append(rel)

    return deduped, notes
