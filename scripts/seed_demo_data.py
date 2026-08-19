#!/usr/bin/env python3
"""Write each adapter's demo fixtures to data/raw/ without running the full
pipeline. Useful for inspecting exactly what fixture data each source
contributes before wiring in real credentials.

Usage: python scripts/seed_demo_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import RAW_DIR
from src.discovery.directories import DirectoriesAdapter
from src.discovery.github import GitHubAdapter
from src.discovery.huggingface import HuggingFaceAdapter
from src.discovery.rss import RSSAdapter
from src.discovery.youtube import YouTubeAdapter
from src.utils.helpers import write_json


def main() -> None:
    adapters = [GitHubAdapter(), HuggingFaceAdapter(), YouTubeAdapter(), RSSAdapter(), DirectoriesAdapter()]
    for adapter in adapters:
        fixtures = adapter.demo_records()
        out_path = RAW_DIR / f"{adapter.source_name.value}.demo.json"
        write_json(out_path, fixtures)
        print(f"wrote {len(fixtures)} fixture record group(s) -> {out_path}")


if __name__ == "__main__":
    main()
