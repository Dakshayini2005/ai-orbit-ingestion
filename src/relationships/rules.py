"""Deterministic relationship rules (spec section 24, "rules first").

Each rule inspects structured metadata already on the entities (no text
parsing here — that's relationships/extractor.py's text-based stage) and
yields candidate (source_id, relationship, target_id, confidence, reason)
tuples. Rules never touch entities directly; they only read.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.entities import Entity
from src.models.enums import RelationshipType
from src.normalization.names import normalize_name


@dataclass
class RelationshipCandidate:
    source_id: str
    relationship: RelationshipType
    target_id: str
    confidence: float
    reason: str
    source_name: str
    source_url: str | None


def github_owner_develops_repository(entities: list[Entity]) -> list[RelationshipCandidate]:
    """GitHub owner -> DEVELOPS -> repository, when the owner matches a
    known Company entity by normalized name.
    """
    companies_by_norm_name = {
        normalize_name(e.name): e for e in entities if e.entity_type == "company"
    }
    candidates = []
    for e in entities:
        if e.entity_type != "repository" or not e.repository_metadata or not e.repository_metadata.owner:
            continue
        owner_norm = normalize_name(e.repository_metadata.owner)
        company = companies_by_norm_name.get(owner_norm)
        if company:
            candidates.append(RelationshipCandidate(
                source_id=company.id, relationship=RelationshipType.DEVELOPS, target_id=e.id,
                confidence=0.97, reason="github_owner", source_name="GitHub", source_url=e.url,
            ))
    return candidates


def huggingface_provider_develops_model(entities: list[Entity]) -> list[RelationshipCandidate]:
    companies_by_norm_name = {
        normalize_name(e.name): e for e in entities if e.entity_type == "company"
    }
    candidates = []
    for e in entities:
        if e.entity_type != "model" or not e.model_metadata or not e.model_metadata.provider:
            continue
        provider_norm = normalize_name(e.model_metadata.provider)
        company = companies_by_norm_name.get(provider_norm)
        if company:
            candidates.append(RelationshipCandidate(
                source_id=company.id, relationship=RelationshipType.DEVELOPS, target_id=e.id,
                confidence=0.95, reason="huggingface_provider", source_name="Hugging Face", source_url=e.url,
            ))
    return candidates


def mcp_server_integrates_with_tool(entities: list[Entity]) -> list[RelationshipCandidate]:
    """Curated MCP servers integrate with the tool/platform named in their
    description (simple containment check against known tool/company names).
    """
    tools = [e for e in entities if e.entity_type in ("tool", "company")]
    candidates = []
    for mcp in entities:
        if mcp.entity_type != "mcp_server":
            continue
        haystack = f"{mcp.name} {mcp.description or ''}".lower()
        for tool in tools:
            if normalize_name(tool.name) and normalize_name(tool.name) in normalize_name(haystack):
                candidates.append(RelationshipCandidate(
                    source_id=mcp.id, relationship=RelationshipType.INTEGRATES_WITH, target_id=tool.id,
                    confidence=0.85, reason="mcp_name_match", source_name="rule", source_url=mcp.url,
                ))
    return candidates


def device_runs_model(entities: list[Entity]) -> list[RelationshipCandidate]:
    """Devices/robots with an explicit model reference in their description."""
    models = [e for e in entities if e.entity_type == "model"]
    candidates = []
    for device in entities:
        if device.entity_type not in ("device", "robot"):
            continue
        haystack = normalize_name(f"{device.name} {device.description or ''}")
        for model in models:
            model_key = normalize_name(model.name)
            if model_key and model_key in haystack:
                candidates.append(RelationshipCandidate(
                    source_id=device.id, relationship=RelationshipType.RUNS, target_id=model.id,
                    confidence=0.85, reason="device_description_match", source_name="rule", source_url=device.url,
                ))
    return candidates


ALL_RULES = [
    github_owner_develops_repository,
    huggingface_provider_develops_model,
    mcp_server_integrates_with_tool,
    device_runs_model,
]
