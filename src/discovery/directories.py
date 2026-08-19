"""AI directories adapter (spec section 15).

Directories are supplementary/cross-reference sources, not authoritative —
enrichment (section 22) prefers official sites over directory data when both
are available. This adapter is also where we source categories that GitHub/
HuggingFace/YouTube/RSS structurally can't produce well: companies, tasks,
robots, devices, personal assistants, creative-generation tools, collections,
and MCP servers as *product listings* (vs. GitHub's MCP *server repos*).

There is no single standardized "AI directory API" with broad free access,
so this adapter's "live" mode queries a small set of public, no-auth JSON
endpoints where available and otherwise degrades to curated demo fixtures —
always clearly marked per spec section 32 (never presented as live data when
it isn't).
"""
from __future__ import annotations

from src.discovery.base import SourceAdapter, SourceRunResult
from src.models.entities import (
    CompanyMetadata, Entity, MCPServerMetadata, SourceInfo, make_entity_id,
)
from src.models.enums import EntityType, SourceName
from src.normalization.urls import normalize_url
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DirectoriesAdapter(SourceAdapter):
    source_name = SourceName.DIRECTORY

    def is_available(self) -> bool:
        # No general-purpose free/no-auth "AI directory API" exists that
        # covers this breadth reliably; document the limitation (spec
        # section 3) and always use the curated fixture set. This IS the
        # graceful-degradation path, applied deliberately rather than as a
        # fallback from a failed live call.
        return False

    def discover(self) -> list[dict]:
        return []

    def fetch(self, item: dict) -> dict:
        raise NotImplementedError("DirectoriesAdapter has no live source configured")

    def normalize(self, raw_data: dict) -> Entity | None:
        return self._build_entity(raw_data)

    def _build_entity(self, spec: dict) -> Entity:
        url = normalize_url(spec["url"])
        entity_type = EntityType(spec["entity_type"])
        entity = Entity(
            id=make_entity_id(entity_type, url or spec["name"]),
            entity_type=entity_type,
            name=spec["name"],
            description=spec.get("description"),
            url=url,
            categories=spec.get("categories", [entity_type.value]),
            source=SourceInfo(name="AI Directory (curated)", url=url),
        )
        if entity_type == EntityType.COMPANY and "company_metadata" in spec:
            entity.company_metadata = CompanyMetadata(**spec["company_metadata"])
        if entity_type == EntityType.MCP_SERVER and "mcp_metadata" in spec:
            entity.mcp_metadata = MCPServerMetadata(**spec["mcp_metadata"])
        return entity

    def demo_records(self) -> list[dict]:
        return _CURATED_DIRECTORY

    def run(self, demo: bool = False) -> SourceRunResult:
        result = SourceRunResult(source=self.source_name, used_demo_fallback=True)
        specs = self.demo_records()
        result.discovered_count = len(specs)
        result.raw_records = specs
        for spec in specs:
            try:
                result.entities.append(self._build_entity(spec))
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"normalize failed for {spec.get('name')}: {exc}")
        logger.info(f"directories run complete: discovered={result.discovered_count} entities={len(result.entities)} demo=True")
        return result


# Curated, hand-maintained cross-reference entries covering categories that
# API-driven sources (GitHub/HF/YouTube/RSS) don't naturally surface:
# companies, tasks, robots, devices, personal assistants, creative tools,
# collections, and product-level MCP listings. Company records here are
# candidates for enrichment (official_sites adapter) before finalization.
_CURATED_DIRECTORY: list[dict] = [
    # Companies
    {"entity_type": "company", "name": "OpenAI", "url": "https://openai.com",
     "description": "AI research and deployment company.", "categories": ["company", "research-lab"],
     "company_metadata": {"founding_year": 2015, "industry_sector": "artificial intelligence", "headquarters": "San Francisco, CA"}},
    {"entity_type": "company", "name": "Anthropic", "url": "https://anthropic.com",
     "description": "AI safety company building Claude.", "categories": ["company", "research-lab"],
     "company_metadata": {"founding_year": 2021, "industry_sector": "artificial intelligence", "headquarters": "San Francisco, CA"}},
    {"entity_type": "company", "name": "Mistral AI", "url": "https://mistral.ai",
     "description": "Open-weight foundation model company.", "categories": ["company"],
     "company_metadata": {"founding_year": 2023, "industry_sector": "artificial intelligence", "headquarters": "Paris, France"}},
    {"entity_type": "company", "name": "Stability AI", "url": "https://stability.ai",
     "description": "Generative media models company.", "categories": ["company"],
     "company_metadata": {"founding_year": 2019, "industry_sector": "generative media", "headquarters": "London, UK"}},
    {"entity_type": "company", "name": "Hugging Face", "url": "https://huggingface.co",
     "description": "Open platform for machine learning models and datasets.", "categories": ["company", "platform"],
     "company_metadata": {"founding_year": 2016, "industry_sector": "ML platform", "headquarters": "New York, NY"}},
    {"entity_type": "company", "name": "Figure AI", "url": "https://figure.ai",
     "description": "Humanoid robotics company.", "categories": ["company", "robotics"],
     "company_metadata": {"founding_year": 2022, "industry_sector": "robotics", "headquarters": "Sunnyvale, CA"}},
    {"entity_type": "company", "name": "Boston Dynamics", "url": "https://bostondynamics.com",
     "description": "Advanced mobile robotics company.", "categories": ["company", "robotics"],
     "company_metadata": {"founding_year": 1992, "industry_sector": "robotics", "headquarters": "Waltham, MA"}},

    # Tasks
    {"entity_type": "task", "name": "Text Summarization", "url": "https://paperswithcode.com/task/text-summarization",
     "description": "Condensing long text into a shorter form while preserving meaning.", "categories": ["task", "nlp"]},
    {"entity_type": "task", "name": "Question Answering", "url": "https://paperswithcode.com/task/question-answering",
     "description": "Producing an answer given a question and optional context.", "categories": ["task", "nlp"]},
    {"entity_type": "task", "name": "Text-to-Image Generation", "url": "https://paperswithcode.com/task/text-to-image-generation",
     "description": "Generating images conditioned on a text prompt.", "categories": ["task", "generative"]},
    {"entity_type": "task", "name": "Code Generation", "url": "https://paperswithcode.com/task/code-generation",
     "description": "Generating source code from natural-language instructions.", "categories": ["task", "coding"]},
    {"entity_type": "task", "name": "Speech Recognition", "url": "https://paperswithcode.com/task/speech-recognition",
     "description": "Transcribing spoken audio into text.", "categories": ["task", "audio"]},
    {"entity_type": "task", "name": "Retrieval-Augmented Generation", "url": "https://paperswithcode.com/task/retrieval-augmented-generation",
     "description": "Grounding generation in retrieved external documents.", "categories": ["task", "nlp"]},

    # Robots / Devices
    {"entity_type": "robot", "name": "Figure 02", "url": "https://figure.ai/figure-02",
     "description": "General-purpose humanoid robot for logistics and manufacturing.", "categories": ["robot", "humanoid"]},
    {"entity_type": "robot", "name": "Boston Dynamics Atlas", "url": "https://bostondynamics.com/atlas",
     "description": "Electric humanoid robot for dynamic mobility research.", "categories": ["robot", "humanoid"]},
    {"entity_type": "robot", "name": "Unitree G1", "url": "https://unitree.com/g1",
     "description": "Compact humanoid robot platform.", "categories": ["robot", "humanoid"]},
    {"entity_type": "device", "name": "NVIDIA Jetson Orin", "url": "https://developer.nvidia.com/embedded/jetson-orin",
     "description": "Edge AI compute module for robotics and embedded inference.", "categories": ["device", "edge-ai"]},
    {"entity_type": "device", "name": "Rabbit R1", "url": "https://rabbit.tech/r1",
     "description": "Dedicated AI assistant hardware device.", "categories": ["device", "personal-assistant-hardware"]},
    {"entity_type": "device", "name": "Humane AI Pin", "url": "https://humane.com/aipin",
     "description": "Wearable AI assistant device.", "categories": ["device", "wearable"]},

    # Personal AI assistants
    {"entity_type": "personal_assistant", "name": "ChatGPT", "url": "https://chatgpt.com",
     "description": "Conversational AI assistant from OpenAI.", "categories": ["personal-assistant"]},
    {"entity_type": "personal_assistant", "name": "Claude", "url": "https://claude.ai",
     "description": "Conversational AI assistant from Anthropic.", "categories": ["personal-assistant"]},
    {"entity_type": "personal_assistant", "name": "Google Gemini", "url": "https://gemini.google.com",
     "description": "Conversational AI assistant from Google.", "categories": ["personal-assistant"]},
    {"entity_type": "personal_assistant", "name": "Perplexity", "url": "https://perplexity.ai",
     "description": "Answer-engine style AI assistant with citations.", "categories": ["personal-assistant", "search"]},

    # Creative-generation tools
    {"entity_type": "creative_tool", "name": "Midjourney", "url": "https://midjourney.com",
     "description": "Text-to-image generation tool known for artistic output.", "categories": ["creative-tool", "image-generation"]},
    {"entity_type": "creative_tool", "name": "Runway", "url": "https://runwayml.com",
     "description": "AI video generation and editing suite.", "categories": ["creative-tool", "video-generation"]},
    {"entity_type": "creative_tool", "name": "ElevenLabs", "url": "https://elevenlabs.io",
     "description": "AI voice generation and cloning platform.", "categories": ["creative-tool", "audio-generation"]},
    {"entity_type": "creative_tool", "name": "Suno", "url": "https://suno.com",
     "description": "AI music generation tool.", "categories": ["creative-tool", "music-generation"]},

    # Collections
    {"entity_type": "collection", "name": "Awesome MCP Servers", "url": "https://github.com/punkpeye/awesome-mcp-servers",
     "description": "Curated list of Model Context Protocol servers.", "categories": ["collection", "mcp"]},
    {"entity_type": "collection", "name": "Awesome LLM Apps", "url": "https://github.com/Shubhamsaboo/awesome-llm-apps",
     "description": "Curated collection of LLM-powered application examples.", "categories": ["collection", "llm"]},
    {"entity_type": "collection", "name": "Hugging Face Open LLM Leaderboard", "url": "https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard",
     "description": "Community leaderboard tracking open-weight LLM benchmarks.", "categories": ["collection", "leaderboard"]},

    # MCP servers/tools (product-level, distinct from GitHub repo entities)
    {"entity_type": "mcp_server", "name": "Filesystem MCP Server", "url": "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
     "description": "Reference MCP server exposing local filesystem access.", "categories": ["mcp-server"],
     "mcp_metadata": {"installation_methods": ["npx", "docker"], "runtime_requirements": ["Node.js 18+"]}},
    {"entity_type": "mcp_server", "name": "GitHub MCP Server", "url": "https://github.com/modelcontextprotocol/servers/tree/main/src/github",
     "description": "MCP server exposing GitHub repository operations.", "categories": ["mcp-server"],
     "mcp_metadata": {"installation_methods": ["npx", "docker"], "runtime_requirements": ["Node.js 18+", "GitHub token"]}},
    {"entity_type": "mcp_server", "name": "Slack MCP Server", "url": "https://github.com/modelcontextprotocol/servers/tree/main/src/slack",
     "description": "MCP server exposing Slack messaging operations.", "categories": ["mcp-server"],
     "mcp_metadata": {"installation_methods": ["npx"], "runtime_requirements": ["Node.js 18+", "Slack bot token"]}},

    # Tools (general AI tools not otherwise categorized)
    {"entity_type": "tool", "name": "LangSmith", "url": "https://smith.langchain.com",
     "description": "Observability and evaluation platform for LLM applications.", "categories": ["tool", "observability"]},
    {"entity_type": "tool", "name": "Weights & Biases", "url": "https://wandb.ai",
     "description": "Experiment tracking platform for ML training runs.", "categories": ["tool", "mlops"]},
    {"entity_type": "tool", "name": "LlamaIndex", "url": "https://llamaindex.ai",
     "description": "Data framework for connecting LLMs to external data.", "categories": ["tool", "rag"]},
]
