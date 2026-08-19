"""Extraction stage.

By the time entities reach this module, each SourceAdapter has already done
discover -> fetch -> normalize (see discovery/base.py). This module's job is
to run every configured adapter with per-source exception isolation, persist
raw responses to the raw-data layer (spec section 16), and hand back a flat
pool of entities plus per-source run stats for the quality report.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import RAW_DIR
from src.discovery.base import SourceAdapter, SourceRunResult
from src.models.entities import Entity
from src.utils.helpers import write_json
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractionSummary:
    entities: list[Entity]
    run_results: list[SourceRunResult]


def run_extraction(adapters: list[SourceAdapter], demo: bool, only_source: str | None = None) -> ExtractionSummary:
    entities: list[Entity] = []
    run_results: list[SourceRunResult] = []

    for adapter in adapters:
        if only_source and adapter.source_name.value != only_source:
            continue

        logger.info(f"extraction: starting source={adapter.source_name.value}")
        try:
            result = adapter.run(demo=demo)
        except Exception as exc:  # noqa: BLE001 — full source-level isolation (spec section 28)
            logger.error(f"extraction: source={adapter.source_name.value} failed entirely: {exc}")
            result = SourceRunResult(source=adapter.source_name, succeeded=False, errors=[str(exc)])

        if result.errors:
            for err in result.errors:
                logger.warning(f"extraction: source={adapter.source_name.value} issue: {err}")

        # Preserve raw responses per spec section 16 (debuggability), never
        # containing secrets since adapters never put tokens in raw payloads.
        if result.raw_records:
            write_json(RAW_DIR / f"{adapter.source_name.value}.json", result.raw_records)

        logger.info(
            f"extraction: source={adapter.source_name.value} discovered={result.discovered_count} "
            f"entities={len(result.entities)} demo_fallback={result.used_demo_fallback} errors={len(result.errors)}"
        )

        entities.extend(result.entities)
        run_results.append(result)

    return ExtractionSummary(entities=entities, run_results=run_results)
