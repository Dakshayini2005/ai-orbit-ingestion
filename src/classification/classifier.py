"""Hybrid classification (spec section 21).

Order of precedence, cheapest/most-deterministic first:
  1. Source metadata already encodes the type (e.g. GitHub adapter already
     set entity_type=REPOSITORY) — nothing to do, just enrich categories.
  2. Rule/keyword matching against name+description+existing categories.
  3. LLM fallback ONLY for entities that remain ambiguous after 1-2 — which,
     given every adapter already sets entity_type deterministically, in
     practice means "add supplementary categories to a known-type entity",
     not "guess the type from scratch". This keeps classification
     deterministic and reproducible for the overwhelming majority of
     records, matching the spec's explicit "do not use an LLM for trivial
     classification" instruction.
"""
from __future__ import annotations

from src.models.entities import Entity
from src.normalization.text import normalize_categories
from src.utils.logging import get_logger

logger = get_logger(__name__)

# keyword -> category, checked against name + description (lowercased)
_KEYWORD_RULES: dict[str, str] = {
    "agent": "ai-agent",
    "mcp": "mcp",
    "diffusion": "image-generation",
    "text-to-image": "image-generation",
    "text-to-video": "video-generation",
    "speech": "audio",
    "voice": "audio",
    "robot": "robotics",
    "humanoid": "robotics",
    "llm": "language-model",
    "reasoning": "language-model",
    "rag": "retrieval",
    "retrieval": "retrieval",
    "chat": "conversational",
    "assistant": "personal-assistant",
    "fine-tun": "training",
    "benchmark": "evaluation",
}


def classify_entity(entity: Entity) -> Entity:
    text = f"{entity.name} {entity.description or ''}".lower()

    rule_categories = [cat for keyword, cat in _KEYWORD_RULES.items() if keyword in text]

    merged = normalize_categories([*entity.categories, entity.entity_type, *rule_categories])
    entity.categories = merged

    if len(entity.categories) <= 1:
        # Ambiguous: only the bare entity_type category present after rules.
        # This is the (rare, given deterministic entity_type assignment)
        # case the spec reserves for optional LLM-assisted classification.
        # We log it rather than call an LLM for every such case, keeping
        # classification cheap and reproducible; a real deployment could
        # wire an LLM call in here behind a flag.
        logger.debug(f"classification: '{entity.name}' has minimal category signal, kept as-is")

    return entity


def classify_entities(entities: list[Entity]) -> list[Entity]:
    return [classify_entity(e) for e in entities]
