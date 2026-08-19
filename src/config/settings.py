"""Centralized configuration loaded from environment variables / .env.

All API credentials are OPTIONAL. Missing credentials disable that source
adapter (or push it into demo/fallback mode) rather than crashing the
pipeline — see discovery/base.py's `is_available` pattern.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SQLITE_PATH = DATA_DIR / "pipeline_cache.sqlite3"


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


@dataclass
class Settings:
    # --- credentials (all optional) ---
    github_token: str | None = field(default_factory=lambda: os.getenv("GITHUB_TOKEN") or None)
    huggingface_token: str | None = field(default_factory=lambda: os.getenv("HUGGINGFACE_TOKEN") or None)
    youtube_api_key: str | None = field(default_factory=lambda: os.getenv("YOUTUBE_API_KEY") or None)

    # --- network / resilience ---
    request_timeout_seconds: float = field(default_factory=lambda: _env_float("REQUEST_TIMEOUT_SECONDS", 15.0))
    max_retries: int = field(default_factory=lambda: _env_int("MAX_RETRIES", 4))
    backoff_base_seconds: float = field(default_factory=lambda: _env_float("BACKOFF_BASE_SECONDS", 1.0))

    # --- entity resolution thresholds (configurable per spec section 19) ---
    fuzzy_match_threshold: float = field(default_factory=lambda: _env_float("FUZZY_MATCH_THRESHOLD", 90.0))
    resolution_confidence_floor: float = field(default_factory=lambda: _env_float("RESOLUTION_CONFIDENCE_FLOOR", 0.80))

    # --- volume targets ---
    target_min_records: int = field(default_factory=lambda: _env_int("TARGET_MIN_RECORDS", 250))
    target_max_records: int = field(default_factory=lambda: _env_int("TARGET_MAX_RECORDS", 300))

    # --- per-source discovery limits (keeps demo/live runs bounded) ---
    github_max_repos: int = field(default_factory=lambda: _env_int("GITHUB_MAX_REPOS", 60))
    huggingface_max_models: int = field(default_factory=lambda: _env_int("HUGGINGFACE_MAX_MODELS", 60))
    youtube_max_videos: int = field(default_factory=lambda: _env_int("YOUTUBE_MAX_VIDEOS", 40))
    rss_max_items_per_feed: int = field(default_factory=lambda: _env_int("RSS_MAX_ITEMS_PER_FEED", 15))

    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    def github_search_queries(self) -> list[str]:
        raw = os.getenv("GITHUB_SEARCH_QUERIES")
        if raw:
            return [q.strip() for q in raw.split(",") if q.strip()]
        return [
            "topic:llm stars:>500",
            "topic:machine-learning stars:>1000",
            "topic:ai-agent stars:>200",
            "topic:mcp-server",
        ]

    def rss_feed_urls(self) -> list[str]:
        raw = os.getenv("RSS_FEED_URLS")
        if raw:
            return [u.strip() for u in raw.split(",") if u.strip()]
        return [
            "https://openai.com/news/rss.xml",
            "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
            "https://www.deepmind.com/blog/rss.xml",
            "https://huggingface.co/blog/feed.xml",
        ]


settings = Settings()
