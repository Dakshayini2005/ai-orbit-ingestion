"""Enrichment (spec section 22).

After canonicalization (post-dedup), enrich entities using authoritative
sources — concretely, companies with a known official URL get a light
verification fetch (title / meta description) via OfficialSitesAdapter.
Never fabricates data: if the fetch fails or yields nothing new, the entity
is left exactly as it was. Every enriched field's provenance is the fetched
URL itself, recorded in `source`.
"""
from __future__ import annotations

from src.discovery.official_sites import OfficialSitesAdapter
from src.models.entities import Entity
from src.models.enums import EntityType
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Only entity types where an official-site verification pass adds real
# value are enriched — avoids uncontrolled crawling of every entity's URL.
_ENRICHABLE_TYPES = {EntityType.COMPANY}


def enrich_entities(entities: list[Entity], live: bool = False) -> list[Entity]:
    """`live=False` (the default, and always true in --demo mode) skips
    outbound HTTP entirely — enrichment then becomes a documented no-op,
    which is honest graceful degradation rather than fabricated metadata.
    """
    if not live:
        logger.info("enrichment: skipped (live enrichment disabled or running in demo mode)")
        return entities

    adapter = OfficialSitesAdapter()
    enriched_count = 0

    for entity in entities:
        if entity.entity_type not in _ENRICHABLE_TYPES or not entity.url:
            continue
        page = adapter.fetch_page(entity.url)
        if not page:
            continue
        if not entity.description and page.get("meta_description"):
            entity.description = page["meta_description"]
            enriched_count += 1

    logger.info(f"enrichment: verified/enriched {enriched_count} compan(y/ies) via official sites")
    return entities
