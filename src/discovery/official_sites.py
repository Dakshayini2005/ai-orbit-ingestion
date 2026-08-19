"""Official product sites adapter (spec section 14).

Used primarily for enrichment/verification, not primary discovery — this
adapter does not mint new entities. Instead it exposes `fetch_page()`, which
the enrichment stage (src/enrichment/enricher.py) calls for a *specific*
already-known company/tool URL to pull a page title / meta description as a
light verification signal. It performs no uncontrolled crawling: one request
per already-known URL, a real timeout, and no link-following.
"""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from src.config.settings import settings
from src.discovery.base import SourceAdapter, SourceRunResult
from src.models.enums import SourceName
from src.utils.logging import get_logger
from src.utils.retry import http_retry, SourceUnavailableError

logger = get_logger(__name__)


class OfficialSitesAdapter(SourceAdapter):
    """Not a primary-discovery adapter — see enrichment/enricher.py for how
    this is actually used. Implements SourceAdapter for architectural
    consistency (spec section 9) but discover()/run() are no-ops here.
    """

    source_name = SourceName.OFFICIAL_SITE

    def is_available(self) -> bool:
        return True

    def discover(self) -> list:
        return []

    def fetch(self, item) -> dict:
        raise NotImplementedError("use fetch_page(url) for targeted enrichment fetches")

    def normalize(self, raw_data: dict):
        return None

    def run(self, demo: bool = False) -> SourceRunResult:
        # This adapter contributes no entities of its own; it's consumed
        # on-demand by enrichment.
        return SourceRunResult(source=self.source_name, used_demo_fallback=demo)

    @http_retry()
    def fetch_page(self, url: str) -> dict | None:
        """One respectful GET against a known official URL. Returns a small
        dict of {title, meta_description} or None on any failure — this is
        an enrichment nicety, not a required source, so failures degrade
        silently and are logged, not raised further up.
        """
        try:
            with httpx.Client(
                timeout=settings.request_timeout_seconds, follow_redirects=True
            ) as client:
                resp = client.get(url, headers={"User-Agent": "ai-orbit-ingestion/1.0 (+enrichment)"})
            if resp.status_code >= 400:
                raise SourceUnavailableError(f"official site fetch error {resp.status_code} for {url}")
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else None
            meta = soup.find("meta", attrs={"name": "description"})
            meta_description = meta.get("content", "").strip() if meta else None
            return {"title": title, "meta_description": meta_description}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"official_sites: enrichment fetch failed for {url}: {exc}")
            return None
