from src.models.entities import Entity, SourceInfo, make_entity_id
from src.models.enums import EntityType
from src.resolution.deduplicator import deduplicate


def _repo(name: str, url: str, source_name: str) -> Entity:
    return Entity(
        id=make_entity_id(EntityType.REPOSITORY, url),
        entity_type=EntityType.REPOSITORY,
        name=name,
        url=url,
        categories=["repository"],
        source=SourceInfo(name=source_name),
    )


def test_cross_source_duplicates_are_merged_not_just_dropped():
    entities = [
        _repo("transformers", "https://github.com/huggingface/transformers", "GitHub"),
        _repo("transformers", "https://github.com/huggingface/transformers", "Directory"),
        _repo("transformers", "https://www.github.com/huggingface/transformers/", "Official Site"),
    ]
    summary = deduplicate(entities)
    assert len(summary.deduplicated_entities) == 1
    assert summary.duplicates_merged == 2
    # audit trail must contain real provenance, not just a count
    assert all(record.canonical_id for record in summary.audit_trail)


def test_dedup_only_compares_within_same_entity_type():
    from src.models.entities import ModelMetadata

    repo = _repo("Claude", "https://github.com/anthropics/claude", "GitHub")
    model = Entity(
        id=make_entity_id(EntityType.MODEL, "https://huggingface.co/anthropic/claude"),
        entity_type=EntityType.MODEL,
        name="Claude",
        url="https://huggingface.co/anthropic/claude",
        categories=["model"],
        source=SourceInfo(name="Hugging Face"),
        model_metadata=ModelMetadata(provider="anthropic"),
    )
    summary = deduplicate([repo, model])
    assert len(summary.deduplicated_entities) == 2


def test_no_duplicates_present_leaves_all_entities_intact():
    entities = [
        _repo("langchain", "https://github.com/langchain-ai/langchain", "GitHub"),
        _repo("llama_index", "https://github.com/run-llama/llama_index", "GitHub"),
    ]
    summary = deduplicate(entities)
    assert len(summary.deduplicated_entities) == 2
    assert summary.duplicates_merged == 0
