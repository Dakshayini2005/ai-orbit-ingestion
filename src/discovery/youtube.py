"""YouTube discovery adapter (spec section 12).

Requires YOUTUBE_API_KEY (official YouTube Data API v3). Without a key,
`is_available()` returns False and the adapter falls back to deterministic
demo fixtures — this is the source most likely to run in fallback mode
since API keys are the least commonly pre-provisioned.
"""
from __future__ import annotations

import httpx

from src.config.settings import settings
from src.discovery.base import SourceAdapter, SourceRunResult
from src.models.entities import Entity, SourceInfo, VideoMetadata, make_entity_id
from src.models.enums import EntityType, SourceName
from src.normalization.urls import normalize_url
from src.utils.logging import get_logger
from src.utils.retry import http_retry, raise_for_rate_limit, SourceUnavailableError

logger = get_logger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3"
SEARCH_QUERY = "AI model release OR machine learning tutorial 2026"


class YouTubeAdapter(SourceAdapter):
    source_name = SourceName.YOUTUBE

    def is_available(self) -> bool:
        return bool(settings.youtube_api_key)

    @http_retry()
    def _search(self) -> list[dict]:
        with httpx.Client(timeout=settings.request_timeout_seconds) as client:
            resp = client.get(
                f"{API_BASE}/search",
                params={
                    "part": "snippet",
                    "q": SEARCH_QUERY,
                    "type": "video",
                    "maxResults": min(50, settings.youtube_max_videos),
                    "key": settings.youtube_api_key,
                },
            )
        raise_for_rate_limit(resp)
        if resp.status_code >= 400:
            # 403 with quotaExceeded is common; treat as source-unavailable
            # rather than crash the pipeline.
            raise SourceUnavailableError(f"YouTube API error {resp.status_code}: {resp.text[:200]}")
        return resp.json().get("items", [])

    def discover(self) -> list[dict]:
        return [{}]  # single search call covers this adapter's scope

    def fetch(self, item: dict) -> dict:
        return {"results": self._search()}

    def normalize(self, raw_data: dict) -> list[Entity]:  # type: ignore[override]
        entities = []
        for v in raw_data.get("results", []):
            video_id = v.get("id", {}).get("videoId") if isinstance(v.get("id"), dict) else v.get("id")
            if not video_id:
                continue
            snippet = v.get("snippet", {})
            url = normalize_url(f"https://www.youtube.com/watch?v={video_id}")
            entity = Entity(
                id=make_entity_id(EntityType.VIDEO, url),
                entity_type=EntityType.VIDEO,
                name=snippet.get("title", "").strip(),
                description=(snippet.get("description") or "").strip() or None,
                url=url,
                categories=["video"],
                source=SourceInfo(name="YouTube", url=url),
                video_metadata=VideoMetadata(
                    channel=snippet.get("channelTitle"),
                    video_id=video_id,
                    published_date=snippet.get("publishedAt"),
                ),
            )
            entities.append(entity)
        return entities

    def demo_records(self) -> list[dict]:
        fixtures = [
            ("dQw4w9WgXcQ1", "Understanding Transformers From Scratch", "AI Explained", "2026-03-01T00:00:00Z"),
            ("dQw4w9WgXcQ2", "Building Agentic Workflows with MCP", "Two Minute Papers", "2026-04-12T00:00:00Z"),
            ("dQw4w9WgXcQ3", "New Open-Weight Model Release Deep Dive", "Yannic Kilcher", "2026-05-20T00:00:00Z"),
            ("dQw4w9WgXcQ4", "Fine-Tuning LLMs on Consumer Hardware", "Sentdex", "2026-02-14T00:00:00Z"),
            ("dQw4w9WgXcQ5", "RAG Pipelines Explained", "StatQuest", "2026-06-01T00:00:00Z"),
            ("dQw4w9WgXcQ6", "Robotics Foundation Models in 2026", "Lex Fridman", "2026-07-03T00:00:00Z"),
        ]
        results = [
            {
                "id": vid, "snippet": {
                    "title": title, "channelTitle": channel, "publishedAt": pub,
                    "description": f"A technical walkthrough: {title}.",
                },
            }
            for vid, title, channel, pub in fixtures
        ]
        return [{"results": results}]

    def run(self, demo: bool = False) -> SourceRunResult:
        result = SourceRunResult(source=self.source_name)
        use_demo = demo or not self.is_available()
        raw_items = self.demo_records() if use_demo else []
        if not use_demo:
            for ref in self.discover():
                try:
                    raw_items.append(self.fetch(ref))
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"fetch failed: {exc}")
        result.discovered_count = sum(len(r.get("results", [])) for r in raw_items)
        result.raw_records = raw_items
        for raw in raw_items:
            try:
                result.entities.extend(self.normalize(raw))
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"normalize failed: {exc}")
        result.used_demo_fallback = use_demo
        if use_demo and not settings.youtube_api_key:
            logger.info("youtube: no YOUTUBE_API_KEY set, using demo fallback")
        logger.info(f"youtube run complete: discovered={result.discovered_count} entities={len(result.entities)} demo={use_demo}")
        return result
