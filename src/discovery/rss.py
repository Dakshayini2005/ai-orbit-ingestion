"""RSS/News discovery adapter (spec section 13).

Uses feedparser against configurable feed URLs. RSS is a public,
credential-free API surface, so `is_available()` is always True — but
individual feeds can and do fail (dead URL, timeout), which is handled per
feed via exception isolation rather than aborting the whole adapter.
"""
from __future__ import annotations

import feedparser
import httpx

from src.config.settings import settings
from src.discovery.base import SourceAdapter, SourceRunResult
from src.cleaning.cleaner import clean_text
from src.models.entities import Entity, NewsMetadata, SourceInfo, make_entity_id
from src.models.enums import EntityType, SourceName
from src.normalization.urls import normalize_url, extract_domain
from src.utils.logging import get_logger
from src.utils.retry import http_retry, SourceUnavailableError

logger = get_logger(__name__)


class RSSAdapter(SourceAdapter):
    source_name = SourceName.RSS

    def is_available(self) -> bool:
        return True

    @http_retry()
    def _fetch_feed_bytes(self, feed_url: str) -> bytes:
        with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
            resp = client.get(feed_url, headers={"User-Agent": "ai-orbit-ingestion/1.0"})
        if resp.status_code >= 400:
            raise SourceUnavailableError(f"RSS fetch error {resp.status_code} for {feed_url}")
        return resp.content

    def discover(self) -> list[dict]:
        return [{"feed_url": url} for url in settings.rss_feed_urls()]

    def fetch(self, item: dict) -> dict:
        content = self._fetch_feed_bytes(item["feed_url"])
        parsed = feedparser.parse(content)
        entries = parsed.entries[: settings.rss_max_items_per_feed]
        return {"feed_url": item["feed_url"], "publisher": parsed.feed.get("title", extract_domain(item["feed_url"])), "entries": entries}

    def normalize(self, raw_data: dict) -> list[Entity]:  # type: ignore[override]
        entities = []
        publisher = raw_data.get("publisher")
        for entry in raw_data.get("entries", []):
            link = entry.get("link")
            url = normalize_url(link)
            if not url:
                continue
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", "") or entry.get("description", ""))
            if not title:
                continue
            entity = Entity(
                id=make_entity_id(EntityType.NEWS, url),
                entity_type=EntityType.NEWS,
                name=title,
                description=summary or None,
                url=url,
                categories=["news"],
                source=SourceInfo(name=publisher or "RSS", url=raw_data.get("feed_url")),
                news_metadata=NewsMetadata(
                    publisher=publisher,
                    published_date=entry.get("published") or entry.get("updated"),
                ),
            )
            entities.append(entity)
        return entities

    def demo_records(self) -> list[dict]:
        class FakeEntry(dict):
            pass

        feeds = [
            ("OpenAI Blog", "https://openai.com/news/rss.xml", [
                ("New reasoning model achieves state-of-the-art on benchmark suite", "https://openai.com/news/reasoning-model-2026"),
                ("Usage-based pricing update for the API", "https://openai.com/news/pricing-update-2026"),
            ]),
            ("MIT Technology Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed/", [
                ("How AI agents are changing enterprise software", "https://www.technologyreview.com/ai-agents-enterprise-2026"),
                ("The compute bottleneck facing frontier labs", "https://www.technologyreview.com/compute-bottleneck-2026"),
            ]),
            ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", [
                ("Announcing a new open-weight multilingual model family", "https://huggingface.co/blog/multilingual-family-2026"),
            ]),
        ]
        results = []
        for publisher, feed_url, items in feeds:
            entries = [
                {"title": title, "link": link, "summary": f"Coverage of: {title}", "published": "2026-07-15T00:00:00Z"}
                for title, link in items
            ]
            results.append({"feed_url": feed_url, "publisher": publisher, "entries": entries})
        return results

    def run(self, demo: bool = False) -> SourceRunResult:
        result = SourceRunResult(source=self.source_name)
        use_demo = demo
        raw_items: list[dict] = []
        if use_demo:
            raw_items = self.demo_records()
        else:
            any_success = False
            for ref in self.discover():
                try:
                    raw_items.append(self.fetch(ref))
                    any_success = True
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"feed failed ({ref['feed_url']}): {exc}")
            if not any_success:
                logger.warning("rss: all feeds failed, falling back to demo fixtures")
                raw_items = self.demo_records()
                use_demo = True

        result.discovered_count = sum(len(r.get("entries", [])) for r in raw_items)
        result.raw_records = raw_items
        for raw in raw_items:
            try:
                result.entities.extend(self.normalize(raw))
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"normalize failed: {exc}")
        result.used_demo_fallback = use_demo
        logger.info(f"rss run complete: discovered={result.discovered_count} entities={len(result.entities)} demo={use_demo}")
        return result
