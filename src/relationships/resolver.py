"""Combines rule-based + text-based + LLM-assisted candidates, deduplicates,
and produces validated Relationship objects (spec sections 23-26).

Every candidate — regardless of which stage produced it — passes through
`validation/relationship_validator.py` before being accepted. This is the
single choke point that prevents an unvalidated LLM-produced edge (or a
buggy rule) from reaching relationships.json.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.entities import Entity, SourceInfo
from src.models.relationships import Relationship
from src.relationships.extractor import extract_relationships_llm_assisted, extract_text_based
from src.relationships.rules import ALL_RULES, RelationshipCandidate
from src.utils.logging import get_logger
from src.validation.relationship_validator import validate_relationship

logger = get_logger(__name__)


@dataclass
class RelationshipBuildSummary:
    relationships: list[Relationship]
    rejected_count: int
    rejected_reasons: list[str]


def _dedupe_candidates(candidates: list[RelationshipCandidate]) -> list[RelationshipCandidate]:
    seen: dict[tuple[str, str, str], RelationshipCandidate] = {}
    for c in candidates:
        key = (c.source_id, c.relationship.value, c.target_id)
        existing = seen.get(key)
        if existing is None or c.confidence > existing.confidence:
            seen[key] = c
    return list(seen.values())


def build_relationships(entities: list[Entity]) -> RelationshipBuildSummary:
    entity_by_id = {e.id: e for e in entities}

    candidates: list[RelationshipCandidate] = []
    for rule_fn in ALL_RULES:
        candidates.extend(rule_fn(entities))
    candidates.extend(extract_text_based(entities))
    candidates.extend(extract_relationships_llm_assisted(entities))

    candidates = _dedupe_candidates(candidates)

    relationships: list[Relationship] = []
    rejected_reasons: list[str] = []

    for c in candidates:
        try:
            rel = Relationship(
                source_id=c.source_id,
                relationship=c.relationship,
                target_id=c.target_id,
                confidence=c.confidence,
                source=SourceInfo(name=c.source_name, url=c.source_url),
                reason=c.reason,
            )
        except Exception as exc:  # noqa: BLE001 — malformed candidate (e.g. bad confidence)
            rejected_reasons.append(f"construction failed: {exc}")
            continue

        ok, reason = validate_relationship(rel, entity_by_id)
        if ok:
            relationships.append(rel)
        else:
            rejected_reasons.append(reason)
            logger.warning(f"relationships: rejected {c.source_id}->{c.target_id} ({c.relationship.value}): {reason}")

    logger.info(f"relationships: built {len(relationships)} valid, rejected {len(rejected_reasons)}")
    return RelationshipBuildSummary(
        relationships=relationships,
        rejected_count=len(rejected_reasons),
        rejected_reasons=rejected_reasons,
    )
