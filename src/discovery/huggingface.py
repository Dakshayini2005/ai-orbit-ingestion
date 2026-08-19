"""Hugging Face discovery adapter (spec section 11).

Uses the public HF Hub API (`/api/models`), which works without a token for
read access; HUGGINGFACE_TOKEN (if set) raises rate limits.
"""
from __future__ import annotations

import httpx

from src.config.settings import settings
from src.discovery.base import SourceAdapter, SourceRunResult
from src.models.entities import Entity, ModelMetadata, SourceInfo, make_entity_id
from src.models.enums import EntityType, SourceName
from src.normalization.urls import normalize_url
from src.utils.logging import get_logger
from src.utils.retry import http_retry, raise_for_rate_limit, SourceUnavailableError

logger = get_logger(__name__)

API_BASE = "https://huggingface.co/api"


class HuggingFaceAdapter(SourceAdapter):
    source_name = SourceName.HUGGINGFACE

    def is_available(self) -> bool:
        return True  # public reads don't require a token

    def _headers(self) -> dict:
        headers = {}
        if settings.huggingface_token:
            headers["Authorization"] = f"Bearer {settings.huggingface_token}"
        return headers

    @http_retry()
    def _list_models(self, limit: int) -> list[dict]:
        with httpx.Client(timeout=settings.request_timeout_seconds) as client:
            resp = client.get(
                f"{API_BASE}/models",
                headers=self._headers(),
                params={"sort": "downloads", "direction": -1, "limit": limit},
            )
        raise_for_rate_limit(resp)
        if resp.status_code >= 400:
            raise SourceUnavailableError(f"HF API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def discover(self) -> list[dict]:
        return [{"limit": settings.huggingface_max_models}]

    def fetch(self, item: dict) -> dict:
        return {"results": self._list_models(item["limit"])}

    def normalize(self, raw_data: dict) -> list[Entity]:  # type: ignore[override]
        entities = []
        for m in raw_data.get("results", []):
            model_id = m.get("id") or m.get("modelId")
            if not model_id:
                continue
            url = normalize_url(f"https://huggingface.co/{model_id}")
            provider = model_id.split("/")[0] if "/" in model_id else None
            entity = Entity(
                id=make_entity_id(EntityType.MODEL, url),
                entity_type=EntityType.MODEL,
                name=model_id,
                description=f"{m.get('pipeline_tag', 'model')} model on Hugging Face" ,
                url=url,
                categories=["model"] + ([m["pipeline_tag"]] if m.get("pipeline_tag") else []),
                source=SourceInfo(name="Hugging Face", url=url),
                raw_names=[model_id],
                model_metadata=ModelMetadata(
                    license=(m.get("cardData") or {}).get("license") if isinstance(m.get("cardData"), dict) else None,
                    modalities=[m["pipeline_tag"]] if m.get("pipeline_tag") else [],
                    provider=provider,
                    downloads=m.get("downloads"),
                    pipeline_tag=m.get("pipeline_tag"),
                    tags=(m.get("tags") or [])[:10],
                ),
            )
            entities.append(entity)
        return entities

    def demo_records(self) -> list[dict]:
        fixtures = [
            ("meta-llama/Llama-3.1-8B-Instruct", "text-generation", "meta-llama", 5200000, "llama3.1"),
            ("mistralai/Mistral-7B-Instruct-v0.3", "text-generation", "mistralai", 3100000, "apache-2.0"),
            ("stabilityai/stable-diffusion-xl-base-1.0", "text-to-image", "stabilityai", 4800000, "openrail++"),
            ("openai/whisper-large-v3", "automatic-speech-recognition", "openai", 6100000, "apache-2.0"),
            ("google/gemma-2-9b-it", "text-generation", "google", 2200000, "gemma"),
            ("Qwen/Qwen2.5-7B-Instruct", "text-generation", "Qwen", 1800000, "apache-2.0"),
            ("black-forest-labs/FLUX.1-dev", "text-to-image", "black-forest-labs", 2500000, "flux-1-dev-non-commercial"),
            ("sentence-transformers/all-MiniLM-L6-v2", "sentence-similarity", "sentence-transformers", 9800000, "apache-2.0"),
        ]
        results = []
        for model_id, task, provider, downloads, license_ in fixtures:
            results.append({
                "id": model_id, "pipeline_tag": task, "downloads": downloads,
                "tags": [task, provider], "cardData": {"license": license_},
            })
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
        logger.info(f"huggingface run complete: discovered={result.discovered_count} entities={len(result.entities)} demo={use_demo}")
        return result
