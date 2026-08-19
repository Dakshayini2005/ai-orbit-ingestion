"""Multi-stage entity resolution (spec section 19).

Only entities of the SAME entity_type are ever compared — a Model named
"Claude" and a Company named "Claude" are never candidates for merging,
regardless of name similarity, since cross-type merges would corrupt the
schema and the relationship graph.

Stages run in priority order per candidate pair; the first stage that fires
determines the merge confidence and reason. Pairs scoring below
`settings.resolution_confidence_floor` are never auto-merged — they are
recorded as "considered, not merged" in the audit trail for transparency.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.config.settings import settings
from src.models.entities import Entity
from src.models.enums import MergeReason
from src.resolution.similarity import (
    CONFIDENCE_ALIAS,
    CONFIDENCE_EXACT_NAME,
    CONFIDENCE_EXACT_URL,
    CONFIDENCE_FUZZY,
    CONFIDENCE_SEMANTIC,
    alias_match,
    exact_name_match,
    exact_url_match,
    fuzzy_score,
    has_conflicting_tokens,
    loose_name_match,
    semantic_score_stub,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MergeAuditRecord:
    canonical_id: str
    canonical_name: str
    merged_entity_id: str
    merged_entity_name: str
    original_names: list[str]
    matched_names: list[str]
    source_records: list[str]
    confidence: float
    reason: str


@dataclass
class ResolutionResult:
    resolved_entities: list[Entity]
    audit_trail: list[MergeAuditRecord] = field(default_factory=list)


def _find_match(entity: Entity, canonical_pool: list[Entity]) -> tuple[Entity, float, MergeReason] | None:
    """Return the best matching canonical entity for `entity`, or None."""
    best: tuple[Entity, float, MergeReason] | None = None

    for candidate in canonical_pool:
        if candidate.entity_type != entity.entity_type:
            continue

        # Stage 1: exact canonical URL
        if exact_url_match(entity.url, candidate.url):
            score = CONFIDENCE_EXACT_URL
            reason = MergeReason.EXACT_URL
        # Stage 2: exact normalized name
        elif exact_name_match(entity.name, candidate.name):
            score = CONFIDENCE_EXACT_NAME
            reason = MergeReason.EXACT_NAME
        # Stage 3: alias match (against a known aliases list, OR a direct
        # corporate-suffix-stripped match between the two names themselves —
        # see loose_name_match's docstring for why both are needed)
        elif (
            alias_match(entity.name, candidate.aliases)
            or alias_match(candidate.name, entity.aliases)
            or loose_name_match(entity.name, candidate.name)
        ):
            score = CONFIDENCE_ALIAS
            reason = MergeReason.ALIAS
        elif has_conflicting_tokens(entity.name, candidate.name):
            # Hard override: one name has a token the other lacks (beyond
            # corporate-suffix noise) that isn't a spelling variant of
            # anything on the other side — e.g. "8B" vs "0.6B", "L4" vs
            # "L6", an inserted "VL" or "xlm" modality/variant tag. Fuzzy/
            # semantic scoring treats these as highly similar because most
            # OTHER tokens match — exactly backwards, since the differing
            # token is usually what distinguishes two genuinely different
            # releases. Never merge on fuzzy/semantic grounds when this
            # fires; only an exact URL/name/alias match (checked above)
            # can still resolve them together.
            continue
        else:
            # Stage 4: fuzzy match
            fuzzy = fuzzy_score(entity.name, candidate.name)
            if fuzzy >= settings.fuzzy_match_threshold:
                score = CONFIDENCE_FUZZY
                reason = MergeReason.FUZZY
            else:
                # Stage 5: semantic similarity (last resort, lowest confidence)
                semantic = semantic_score_stub(
                    entity.name, candidate.name,
                    entity.description or "", candidate.description or "",
                )
                if semantic >= 0.5:
                    score = CONFIDENCE_SEMANTIC
                    reason = MergeReason.SEMANTIC
                else:
                    continue

        if best is None or score > best[1]:
            best = (candidate, score, reason)

    return best


def resolve_entities(entities: list[Entity]) -> ResolutionResult:
    """Greedy multi-stage resolution: process entities in order, merging each
    into the best-matching existing canonical entity if confidence clears
    the configurable floor, else adding it as a new canonical entity.
    """
    canonical_pool: list[Entity] = []
    audit_trail: list[MergeAuditRecord] = []

    for entity in entities:
        match = _find_match(entity, canonical_pool)

        if match is not None and match[1] >= settings.resolution_confidence_floor:
            canonical, score, reason = match
            # Merge: keep the canonical record, but enrich it with any
            # fields the incoming duplicate has that canonical is missing,
            # and record provenance of the merge.
            canonical.matched_source_records += 1
            if entity.name not in canonical.aliases and entity.name != canonical.name:
                canonical.aliases.append(entity.name)
            canonical.raw_names.extend(entity.raw_names or [entity.name])
            if not canonical.description and entity.description:
                canonical.description = entity.description
            if not canonical.url and entity.url:
                canonical.url = entity.url
            for cat in entity.categories:
                if cat not in canonical.categories:
                    canonical.categories.append(cat)
            # Fill in specialized metadata gaps from the duplicate.
            for field_name in (
                "model_metadata", "repository_metadata", "mcp_metadata",
                "company_metadata", "video_metadata", "news_metadata",
            ):
                if getattr(canonical, field_name) is None and getattr(entity, field_name) is not None:
                    setattr(canonical, field_name, getattr(entity, field_name))

            audit_trail.append(MergeAuditRecord(
                canonical_id=canonical.id,
                canonical_name=canonical.name,
                merged_entity_id=entity.id,
                merged_entity_name=entity.name,
                original_names=[entity.name],
                matched_names=[canonical.name],
                source_records=[entity.source.name],
                confidence=round(score, 3),
                reason=reason.value,
            ))
            logger.info(
                f"resolution: merged '{entity.name}' into '{canonical.name}' "
                f"(reason={reason.value} confidence={score:.2f})"
            )
        else:
            canonical_pool.append(entity)

    return ResolutionResult(resolved_entities=canonical_pool, audit_trail=audit_trail)
