"""Deduplication orchestration (spec section 20).

Explicitly NOT `pandas.drop_duplicates()`. This module:
  1. Groups entities by entity_type (dedup only ever happens within a type).
  2. Runs full multi-stage entity resolution (see resolution/entity_resolver.py)
     within each group, which is what actually recognizes that a GitHub repo,
     a directory listing, and an official-site record describe the same
     underlying entity.
  3. Aggregates the audit trail across groups so the quality report can show
     "duplicates detected" / "duplicates merged" with real provenance.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.models.entities import Entity
from src.resolution.entity_resolver import MergeAuditRecord, resolve_entities
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DeduplicationSummary:
    deduplicated_entities: list[Entity]
    audit_trail: list[MergeAuditRecord]
    duplicates_detected: int
    duplicates_merged: int


def deduplicate(entities: list[Entity]) -> DeduplicationSummary:
    by_type: dict[str, list[Entity]] = defaultdict(list)
    for e in entities:
        by_type[e.entity_type].append(e)

    all_resolved: list[Entity] = []
    all_audit: list[MergeAuditRecord] = []

    for entity_type, group in by_type.items():
        result = resolve_entities(group)
        all_resolved.extend(result.resolved_entities)
        all_audit.extend(result.audit_trail)
        if result.audit_trail:
            logger.info(f"dedup: entity_type={entity_type} merged {len(result.audit_trail)} duplicate(s)")

    return DeduplicationSummary(
        deduplicated_entities=all_resolved,
        audit_trail=all_audit,
        duplicates_detected=len(all_audit),
        duplicates_merged=len(all_audit),
    )
