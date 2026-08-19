"""Pipeline orchestrator: Discovery -> Extraction -> Cleaning -> Normalization
-> Entity Resolution + Deduplication -> Classification -> Enrichment ->
Relationship Engine -> Validation -> outputs.

This is the ONLY module that knows the full stage order. Every stage module
is independently testable and importable on its own (see tests/).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.classification.classifier import classify_entities
from src.cleaning.cleaner import clean_text, is_empty_description
from src.config.settings import DATA_DIR, settings
from src.discovery.directories import DirectoriesAdapter
from src.discovery.github import GitHubAdapter
from src.discovery.huggingface import HuggingFaceAdapter
from src.discovery.rss import RSSAdapter
from src.discovery.youtube import YouTubeAdapter
from src.enrichment.enricher import enrich_entities
from src.extraction.extractor import run_extraction
from src.models.entities import Entity
from src.normalization.text import normalize_categories
from src.normalization.urls import normalize_url
from src.relationships.resolver import build_relationships
from src.resolution.deduplicator import deduplicate
from src.storage import sqlite as storage
from src.utils.helpers import write_json
from src.utils.logging import get_logger
from src.validation.entity_validator import validate_entities
from src.validation.quality import build_quality_report
from src.validation.relationship_validator import validate_relationship_graph

logger = get_logger(__name__)

ALL_ADAPTERS = [GitHubAdapter(), HuggingFaceAdapter(), YouTubeAdapter(), RSSAdapter(), DirectoriesAdapter()]


@dataclass
class PipelineOutputs:
    entities_path: str
    relationships_path: str
    quality_report_path: str
    quality_report: object


def _clean_entity(entity: Entity) -> Entity:
    entity.name = clean_text(entity.name) or entity.name
    if is_empty_description(entity.description):
        entity.description = None
    else:
        entity.description = clean_text(entity.description)
    return entity


def _normalize_entity(entity: Entity) -> Entity:
    entity.url = normalize_url(entity.url)
    entity.categories = normalize_categories(entity.categories)
    return entity


def run_pipeline(demo: bool = False, only_source: str | None = None, resume: bool = False, live_enrichment: bool = False) -> PipelineOutputs:
    logger.info(f"pipeline: starting (demo={demo}, only_source={only_source}, resume={resume})")

    with storage.get_connection() as conn:
        run_id = storage.start_run(conn, mode="demo" if demo else "live")

        # --- Discovery + Extraction ---
        adapters = ALL_ADAPTERS if not only_source else [a for a in ALL_ADAPTERS if a.source_name.value == only_source]
        extraction = run_extraction(adapters, demo=demo, only_source=only_source)
        discovered_count = sum(r.discovered_count for r in extraction.run_results)
        for r in extraction.run_results:
            storage.record_source_status(
                conn, run_id, r.source.value, r.discovered_count, len(r.entities),
                r.used_demo_fallback, r.succeeded, r.errors,
            )

        raw_entities = extraction.entities
        logger.info(f"pipeline: extraction complete, {len(raw_entities)} raw entities from {discovered_count} discovered items")

        # --- Cleaning ---
        cleaned_entities = [_clean_entity(e) for e in raw_entities]
        cleaned_entities = [e for e in cleaned_entities if e.name]  # drop anything cleaning emptied out
        logger.info(f"pipeline: cleaning complete, {len(cleaned_entities)} entities remain")

        # --- Normalization ---
        normalized_entities = [_normalize_entity(e) for e in cleaned_entities]
        logger.info(f"pipeline: normalization complete, {len(normalized_entities)} entities")

        # --- Entity Resolution + Deduplication ---
        dedup = deduplicate(normalized_entities)
        logger.info(
            f"pipeline: dedup complete, {dedup.duplicates_merged} duplicates merged, "
            f"{len(dedup.deduplicated_entities)} canonical entities remain"
        )

        # --- Classification ---
        classified_entities = classify_entities(dedup.deduplicated_entities)

        # --- Enrichment ---
        enriched_entities = enrich_entities(classified_entities, live=live_enrichment)

        # --- Validation (entities) ---
        valid_entities, invalid_entity_reasons = validate_entities(enriched_entities)
        logger.info(f"pipeline: entity validation complete, {len(valid_entities)} valid, {len(invalid_entity_reasons)} invalid")

        storage.upsert_entities(conn, [e.model_dump() for e in valid_entities])

        # --- Relationship Engine ---
        rel_build = build_relationships(valid_entities)

        # --- Validation (relationships / graph consistency) ---
        final_relationships, graph_notes = validate_relationship_graph(rel_build.relationships)
        for note in graph_notes:
            logger.warning(f"pipeline: {note}")

        storage.record_relationship_candidates(conn, [
            {"source_id": r.source_id, "relationship": r.relationship, "target_id": r.target_id,
             "confidence": r.confidence, "accepted": True, "reason": r.reason}
            for r in final_relationships
        ])

        # --- Quality Report ---
        report = build_quality_report(
            discovered_count=discovered_count,
            cleaned_count=len(cleaned_entities),
            normalized_count=len(normalized_entities),
            dedup_detected=dedup.duplicates_detected,
            dedup_merged=dedup.duplicates_merged,
            final_entities=valid_entities,
            invalid_entity_reasons=invalid_entity_reasons,
            relationships=final_relationships,
            invalid_relationship_count=rel_build.rejected_count,
            source_run_results=extraction.run_results,
        )

        storage.finish_run(conn, run_id, len(valid_entities), len(final_relationships))

    # --- Write outputs ---
    entities_path = DATA_DIR / "entities.json"
    relationships_path = DATA_DIR / "relationships.json"
    quality_report_path = DATA_DIR / "quality_report.json"

    write_json(entities_path, [e.model_dump() for e in valid_entities])
    write_json(relationships_path, [r.model_dump() for r in final_relationships])
    write_json(quality_report_path, report.to_dict())

    print(report.render_console())
    logger.info("pipeline: complete")

    return PipelineOutputs(
        entities_path=str(entities_path),
        relationships_path=str(relationships_path),
        quality_report_path=str(quality_report_path),
        quality_report=report,
    )
