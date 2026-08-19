"""Common source adapter interface (spec section 9).

Every source implements discover() -> fetch() -> normalize() so the
orchestrator never contains source-specific branching logic. Adding a new
source means adding one new file in src/discovery/, nothing else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.models.entities import Entity
from src.models.enums import SourceName


@dataclass
class SourceRunResult:
    """What the orchestrator gets back from running one adapter."""

    source: SourceName
    entities: list[Entity] = field(default_factory=list)
    raw_records: list[dict] = field(default_factory=list)
    discovered_count: int = 0
    errors: list[str] = field(default_factory=list)
    used_demo_fallback: bool = False
    succeeded: bool = True


class SourceAdapter(ABC):
    """Base class every discovery/*.py adapter must implement."""

    source_name: SourceName

    @abstractmethod
    def is_available(self) -> bool:
        """Whether live credentials/config are present for this source."""

    @abstractmethod
    def discover(self) -> list[Any]:
        """Return a list of lightweight references to items worth fetching."""

    @abstractmethod
    def fetch(self, item: Any) -> dict:
        """Fetch full raw data for one discovered item."""

    @abstractmethod
    def normalize(self, raw_data: dict) -> Entity | None:
        """Convert one raw record into a canonical Entity (or None to skip)."""

    def demo_records(self) -> list[dict]:
        """Deterministic fixture records used when live credentials are
        unavailable (spec section 32). Subclasses override this."""
        return []

    def run(self, demo: bool = False) -> SourceRunResult:
        """Template method: discover -> fetch -> normalize, with per-item
        exception isolation so one bad record never aborts the whole source,
        and per-source exception isolation so one bad source never aborts
        the whole pipeline (handled by the orchestrator around this call).
        """
        result = SourceRunResult(source=self.source_name)

        use_demo = demo or not self.is_available()
        result.used_demo_fallback = use_demo and demo is False

        raw_items: list[dict]
        if use_demo:
            raw_items = self.demo_records()
        else:
            raw_items = []
            for ref in self.discover():
                try:
                    raw_items.append(self.fetch(ref))
                except Exception as exc:  # noqa: BLE001 - isolate per-item failures
                    result.errors.append(f"fetch failed for {ref!r}: {exc}")

        result.discovered_count = len(raw_items)
        result.raw_records = raw_items

        for raw in raw_items:
            try:
                entity = self.normalize(raw)
                if entity is not None:
                    result.entities.append(entity)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"normalize failed: {exc}")

        return result
