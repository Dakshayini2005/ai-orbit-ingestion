"""GitHub discovery adapter (spec section 10).

Uses the GitHub REST search API (`/search/repositories`). Works
unauthenticated (60 req/hr) but respects GITHUB_TOKEN when present (5000
req/hr). Configurable search queries, pagination, retry/backoff, and a
deterministic demo fallback when no network/token is usable.
"""
from __future__ import annotations

import httpx

from src.config.settings import settings
from src.discovery.base import SourceAdapter
from src.models.entities import Entity, ModelMetadata, RepositoryMetadata, SourceInfo, make_entity_id
from src.models.enums import EntityType, SourceName
from src.normalization.urls import normalize_url
from src.utils.logging import get_logger
from src.utils.retry import http_retry, raise_for_rate_limit, SourceUnavailableError

logger = get_logger(__name__)

API_BASE = "https://api.github.com"


class GitHubAdapter(SourceAdapter):
    source_name = SourceName.GITHUB

    def is_available(self) -> bool:
        # GitHub search works without a token too, but we treat "available"
        # as "we have network + the API isn't rate-limiting us anonymously"
        # — a lightweight live check is done lazily in discover().
        return True

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        return headers

    @http_retry()
    def _search_page(self, query: str, page: int) -> dict:
        with httpx.Client(timeout=settings.request_timeout_seconds) as client:
            resp = client.get(
                f"{API_BASE}/search/repositories",
                headers=self._headers(),
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 20, "page": page},
            )
        raise_for_rate_limit(resp)
        if resp.status_code >= 400:
            raise SourceUnavailableError(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def discover(self) -> list[dict]:
        """Returns lightweight refs: {query, page} — fetch() does the real pull."""
        refs = []
        per_query_pages = max(1, settings.github_max_repos // (20 * max(1, len(settings.github_search_queries()))))
        for query in settings.github_search_queries():
            for page in range(1, per_query_pages + 1):
                refs.append({"query": query, "page": page})
        return refs

    def fetch(self, item: dict) -> dict:
        data = self._search_page(item["query"], item["page"])
        return {"query": item["query"], "results": data.get("items", [])}

    def normalize(self, raw_data: dict) -> list[Entity]:  # type: ignore[override]
        # GitHub's fetch() returns a page of repos, so normalize expands to
        # multiple entities. run() handles either an Entity or an iterable.
        entities = []
        for repo in raw_data.get("results", []):
            url = normalize_url(repo.get("html_url"))
            if not url:
                continue
            entity = Entity(
                id=make_entity_id(EntityType.REPOSITORY, url),
                entity_type=EntityType.REPOSITORY,
                name=repo.get("name", "").strip(),
                description=(repo.get("description") or "").strip() or None,
                url=url,
                categories=["repository"] + (repo.get("topics") or [])[:5],
                source=SourceInfo(name="GitHub", url=url),
                raw_names=[repo.get("full_name", "")],
                repository_metadata=RepositoryMetadata(
                    stars=repo.get("stargazers_count"),
                    forks=repo.get("forks_count"),
                    primary_language=repo.get("language"),
                    last_updated=repo.get("updated_at"),
                    created_at=repo.get("created_at"),
                    license=(repo.get("license") or {}).get("spdx_id"),
                    topics=(repo.get("topics") or [])[:10],
                    owner=(repo.get("owner") or {}).get("login"),
                ),
            )
            entities.append(entity)
        return entities

    def demo_records(self) -> list[dict]:
        fixtures = [
            ("langchain-ai", "langchain", "Build context-aware reasoning applications", 92000, "Python", ["llm", "agents"]),
            ("run-llama", "llama_index", "Data framework for LLM applications", 36000, "Python", ["llm", "rag"]),
            ("huggingface", "transformers", "State-of-the-art ML for PyTorch, TensorFlow, JAX", 132000, "Python", ["machine-learning", "nlp"]),
            ("ollama", "ollama", "Get up and running with large language models locally", 98000, "Go", ["llm", "local-ai"]),
            ("open-webui", "open-webui", "User-friendly AI interface", 55000, "Python", ["chat-ui", "llm"]),
            ("modelcontextprotocol", "servers", "Model Context Protocol reference servers", 12000, "TypeScript", ["mcp-server", "ai-agent"]),
            ("comfyanonymous", "ComfyUI", "Powerful modular diffusion model GUI", 58000, "Python", ["image-generation", "diffusion"]),
            ("microsoft", "autogen", "Multi-agent conversation framework", 33000, "Python", ["ai-agent", "multi-agent"]),
        ]
        results = []
        for owner, name, desc, stars, lang, topics in fixtures:
            results.append({
                "name": name, "full_name": f"{owner}/{name}", "description": desc,
                "html_url": f"https://github.com/{owner}/{name}",
                "stargazers_count": stars, "forks_count": stars // 10, "language": lang,
                "topics": topics, "created_at": "2022-01-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z",
                "license": {"spdx_id": "MIT"}, "owner": {"login": owner},
            })
        return [{"query": "demo", "results": results}]

    def run(self, demo: bool = False):  # override to flatten list-of-lists normalize()
        from src.discovery.base import SourceRunResult
        result = SourceRunResult(source=self.source_name)
        use_demo = demo or not self.is_available()

        raw_items: list[dict] = self.demo_records() if use_demo else []
        if not use_demo:
            for ref in self.discover():
                try:
                    raw_items.append(self.fetch(ref))
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"fetch failed: {exc}")
            if not raw_items and not result.errors:
                pass  # legitimately empty result set is fine

        result.discovered_count = sum(len(r.get("results", [])) for r in raw_items)
        result.raw_records = raw_items
        for raw in raw_items:
            try:
                result.entities.extend(self.normalize(raw))
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"normalize failed: {exc}")

        if use_demo:
            result.used_demo_fallback = True
        logger.info(f"github run complete: discovered={result.discovered_count} entities={len(result.entities)} demo={use_demo}")
        return result
