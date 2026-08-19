"""Data quality report (spec section 34)."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

from src.discovery.base import SourceRunResult
from src.models.entities import Entity
from src.models.relationships import Relationship


@dataclass
class QualityReport:
    total_discovered: int
    total_after_cleaning: int
    total_after_normalization: int
    duplicates_detected: int
    duplicates_merged: int
    final_entity_count: int
    entities_by_type: dict[str, int]
    entities_by_source: dict[str, int]
    missing_required_fields: int
    invalid_urls: int
    invalid_entities: int
    invalid_relationships: int
    relationship_counts: dict[str, int]
    validation_failures: list[str] = field(default_factory=list)
    source_run_notes: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def render_console(self) -> str:
        lines = [
            "=====================================",
            "AI ORBIT INGESTION REPORT",
            "=====================================",
            "",
            f"Discovered:             {self.total_discovered}",
            f"After cleaning:         {self.total_after_cleaning}",
            f"After normalization:    {self.total_after_normalization}",
            f"Duplicates detected:    {self.duplicates_detected}",
            f"Duplicates merged:      {self.duplicates_merged}",
            f"Final entities:         {self.final_entity_count}",
            f"Relationships:          {sum(self.relationship_counts.values())}",
            "",
            "Validation:",
            f"  Valid entities:       {self.final_entity_count}",
            f"  Invalid entities:     {self.invalid_entities}",
            f"  Invalid relationships:{self.invalid_relationships}",
            "",
            "Entities by type:",
        ]
        for t, count in sorted(self.entities_by_type.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {t:<22}{count}")
        lines.append("")
        lines.append("Entities by source:")
        for s, count in sorted(self.entities_by_source.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {s:<22}{count}")
        if self.relationship_counts:
            lines.append("")
            lines.append("Relationships by type:")
            for r, count in sorted(self.relationship_counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"  {r:<22}{count}")
        return "\n".join(lines)


def build_quality_report(
    *,
    discovered_count: int,
    cleaned_count: int,
    normalized_count: int,
    dedup_detected: int,
    dedup_merged: int,
    final_entities: list[Entity],
    invalid_entity_reasons: dict[str, list[str]],
    relationships: list[Relationship],
    invalid_relationship_count: int,
    source_run_results: list[SourceRunResult],
) -> QualityReport:
    entities_by_type = Counter(
        e.entity_type if isinstance(e.entity_type, str) else e.entity_type.value for e in final_entities
    )
    entities_by_source = Counter(e.source.name for e in final_entities)
    relationship_counts = Counter(
        r.relationship if isinstance(r.relationship, str) else r.relationship.value for r in relationships
    )

    missing_fields = sum(1 for reasons in invalid_entity_reasons.values() if any("missing" in r or "no categories" in r for r in reasons))
    invalid_urls = sum(1 for reasons in invalid_entity_reasons.values() if any("invalid url" in r for r in reasons))

    validation_failures = [f"{eid}: {'; '.join(reasons)}" for eid, reasons in invalid_entity_reasons.items()]

    source_run_notes = {
        r.source.value: {
            "discovered": r.discovered_count,
            "entities": len(r.entities),
            "used_demo_fallback": r.used_demo_fallback,
            "errors": r.errors,
            "succeeded": r.succeeded,
        }
        for r in source_run_results
    }

    return QualityReport(
        total_discovered=discovered_count,
        total_after_cleaning=cleaned_count,
        total_after_normalization=normalized_count,
        duplicates_detected=dedup_detected,
        duplicates_merged=dedup_merged,
        final_entity_count=len(final_entities),
        entities_by_type=dict(entities_by_type),
        entities_by_source=dict(entities_by_source),
        missing_required_fields=missing_fields,
        invalid_urls=invalid_urls,
        invalid_entities=len(invalid_entity_reasons),
        invalid_relationships=invalid_relationship_count,
        relationship_counts=dict(relationship_counts),
        validation_failures=validation_failures,
        source_run_notes=source_run_notes,
    )
