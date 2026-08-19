"""Text-based + LLM-assisted relationship extraction (spec section 24).

Text-based stage: looks for "solves"-style task associations by matching
Task entity names appearing in a Tool/Model's description — a cheap,
deterministic pattern that catches a meaningful chunk of SOLVES edges
without any model calls.

LLM-assisted stage: intentionally NOT wired to a live LLM call in this
project. The spec requires that when it IS used, output must be strict
structured JSON and every extracted relationship must still pass through
the same validation as rule-based ones — "never allow an LLM to directly
write arbitrary JSON into the final dataset without validation." Rather
than fabricate an LLM integration with no real ambiguous-case corpus to
justify it, this module documents the extension point
(`extract_relationships_llm_assisted`) and leaves it as a clearly-marked
no-op, consistent with "use an LLM only for ambiguous/unstructured cases" —
in this dataset's scale, the deterministic + text-based stages already
cover the required relationship types.
"""
from __future__ import annotations

from src.models.entities import Entity
from src.models.enums import RelationshipType
from src.normalization.names import normalize_name
from src.relationships.rules import RelationshipCandidate
from src.utils.logging import get_logger

logger = get_logger(__name__)


def extract_text_based(entities: list[Entity]) -> list[RelationshipCandidate]:
    tasks = [e for e in entities if e.entity_type == "task"]
    solvers = [e for e in entities if e.entity_type in ("tool", "model", "creative_tool", "personal_assistant")]

    candidates = []
    for solver in solvers:
        haystack = normalize_name(f"{solver.name} {solver.description or ''}")
        for task in tasks:
            task_key = normalize_name(task.name)
            if task_key and len(task_key) > 4 and task_key in haystack:
                candidates.append(RelationshipCandidate(
                    source_id=solver.id, relationship=RelationshipType.SOLVES, target_id=task.id,
                    confidence=0.75, reason="text_extraction", source_name="text_match", source_url=solver.url,
                ))
    return candidates


def extract_relationships_llm_assisted(entities: list[Entity]) -> list[RelationshipCandidate]:
    """Documented extension point — see module docstring. Returns no
    candidates by default; a real deployment would call an LLM here with a
    strict JSON schema, then feed the result through the exact same
    validation path as every other candidate (see relationships/resolver.py
    and validation/relationship_validator.py) before it could ever reach
    relationships.json.
    """
    logger.debug("relationships: LLM-assisted extraction stage is a documented no-op in this build")
    return []
