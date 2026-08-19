"""Enumerations shared across the pipeline.

Keeping these centralized means every stage (classification, validation,
relationship extraction) references the same canonical vocabulary instead of
re-declaring string literals in five different modules.
"""
from __future__ import annotations

from enum import Enum


class EntityType(str, Enum):
    """The required data categories from the project specification."""

    TOOL = "tool"
    TASK = "task"
    COMPANY = "company"
    NEWS = "news"
    VIDEO = "video"
    ROBOT = "robot"
    DEVICE = "device"
    MODEL = "model"
    REPOSITORY = "repository"
    MCP_SERVER = "mcp_server"
    COLLECTION = "collection"
    PERSONAL_ASSISTANT = "personal_assistant"
    CREATIVE_TOOL = "creative_tool"


class SourceName(str, Enum):
    GITHUB = "github"
    HUGGINGFACE = "huggingface"
    YOUTUBE = "youtube"
    RSS = "rss"
    OFFICIAL_SITE = "official_site"
    DIRECTORY = "directory"
    DEMO_FIXTURE = "demo_fixture"


class RelationshipType(str, Enum):
    """Minimum required relationship vocabulary. Extend, don't repurpose."""

    DEVELOPS = "DEVELOPS"          # Company -> Tool/Model/Repository
    SOLVES = "SOLVES"              # Tool -> Task
    INTEGRATES_WITH = "INTEGRATES_WITH"  # MCP server -> Tool
    RUNS = "RUNS"                  # Device/Robot -> Model


# Which (source_type, target_type) pairs are semantically valid for each
# relationship. Used by relationship validation to reject nonsensical edges
# (e.g. a NEWS article "DEVELOPS" a Company).
VALID_RELATIONSHIP_TYPE_PAIRS: dict[RelationshipType, set[tuple[EntityType, EntityType]]] = {
    RelationshipType.DEVELOPS: {
        (EntityType.COMPANY, EntityType.TOOL),
        (EntityType.COMPANY, EntityType.MODEL),
        (EntityType.COMPANY, EntityType.REPOSITORY),
        (EntityType.COMPANY, EntityType.DEVICE),
        (EntityType.COMPANY, EntityType.ROBOT),
        (EntityType.COMPANY, EntityType.PERSONAL_ASSISTANT),
        (EntityType.COMPANY, EntityType.CREATIVE_TOOL),
        (EntityType.COMPANY, EntityType.MCP_SERVER),
    },
    RelationshipType.SOLVES: {
        (EntityType.TOOL, EntityType.TASK),
        (EntityType.MODEL, EntityType.TASK),
        (EntityType.CREATIVE_TOOL, EntityType.TASK),
        (EntityType.PERSONAL_ASSISTANT, EntityType.TASK),
    },
    RelationshipType.INTEGRATES_WITH: {
        (EntityType.MCP_SERVER, EntityType.TOOL),
        (EntityType.MCP_SERVER, EntityType.MODEL),
    },
    RelationshipType.RUNS: {
        (EntityType.DEVICE, EntityType.MODEL),
        (EntityType.ROBOT, EntityType.MODEL),
    },
}


class MergeReason(str, Enum):
    EXACT_URL = "exact_url"
    EXACT_NAME = "exact_normalized_name"
    ALIAS = "alias_match"
    FUZZY = "fuzzy_match"
    SEMANTIC = "semantic_similarity"
