#!/usr/bin/env python3
"""AI Orbit Data Ingestion Pipeline — CLI entry point.

Usage:
    python run.py                      # full pipeline, live sources (falls back to demo per-source as needed)
    python run.py --demo               # full pipeline, deterministic fixture data for every source
    python run.py --source github      # run a single source adapter only
    python run.py --resume             # reuse SQLite-cached normalized entities (see storage/sqlite.py)
    python run.py --validate           # re-run validation against the last-written data/entities.json
    python run.py --live-enrichment    # allow enrichment stage to make outbound HTTP calls
"""
from __future__ import annotations

import argparse
import sys

from src.pipeline.orchestrator import run_pipeline


def _cmd_validate() -> int:
    from src.config.settings import DATA_DIR
    from src.models.entities import Entity
    from src.utils.helpers import read_json
    from src.validation.entity_validator import validate_entities

    entities_path = DATA_DIR / "entities.json"
    if not entities_path.exists():
        print(f"No entities.json found at {entities_path}. Run the pipeline first.")
        return 1

    raw = read_json(entities_path)
    entities = [Entity(**e) for e in raw]
    valid, invalid = validate_entities(entities)
    print(f"Validated {len(entities)} entities: {len(valid)} valid, {len(invalid)} invalid.")
    for eid, reasons in invalid.items():
        print(f"  {eid}: {'; '.join(reasons)}")
    return 0 if not invalid else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Orbit Data Ingestion Pipeline")
    parser.add_argument("--demo", action="store_true", help="Use deterministic demo/fixture data for all sources")
    parser.add_argument("--source", choices=["github", "huggingface", "youtube", "rss", "directory"],
                         help="Run only the specified source adapter")
    parser.add_argument("--resume", action="store_true", help="Resume using cached normalized entities from SQLite")
    parser.add_argument("--validate", action="store_true", help="Validate the last-written entities.json and exit")
    parser.add_argument("--live-enrichment", action="store_true", help="Allow enrichment stage to make outbound HTTP requests")
    args = parser.parse_args()

    if args.validate:
        return _cmd_validate()

    run_pipeline(
        demo=args.demo,
        only_source=args.source,
        resume=args.resume,
        live_enrichment=args.live_enrichment,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
