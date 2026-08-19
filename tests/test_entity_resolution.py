from src.models.entities import Entity, SourceInfo, make_entity_id
from src.models.enums import EntityType
from src.resolution.entity_resolver import resolve_entities


def _company(name: str, url: str | None, source_name: str = "directory") -> Entity:
    return Entity(
        id=make_entity_id(EntityType.COMPANY, url or name),
        entity_type=EntityType.COMPANY,
        name=name,
        description=None,
        url=url,
        categories=["company"],
        source=SourceInfo(name=source_name),
    )


def test_exact_url_match_resolves_to_one_entity():
    entities = [
        _company("OpenAI", "https://openai.com"),
        _company("OpenAI", "https://www.openai.com/"),
    ]
    result = resolve_entities(entities)
    assert len(result.resolved_entities) == 1
    assert result.audit_trail[0].reason == "exact_url"


def test_case_variant_names_resolve_together():
    entities = [
        _company("OpenAI", None),
        _company("openai", None),
        _company("OPENAI", None),
    ]
    result = resolve_entities(entities)
    assert len(result.resolved_entities) == 1


def test_open_ai_spacing_variant_resolves_via_fuzzy_or_alias():
    entities = [
        _company("OpenAI", "https://openai.com"),
        _company("Open AI", None),
    ]
    result = resolve_entities(entities)
    # "Open AI" without a URL should fuzzy/alias-match onto the canonical
    # "OpenAI" record rather than remaining a separate entity.
    assert len(result.resolved_entities) == 1


def test_different_companies_do_not_merge():
    entities = [
        _company("OpenAI", "https://openai.com"),
        _company("Anthropic", "https://anthropic.com"),
    ]
    result = resolve_entities(entities)
    assert len(result.resolved_entities) == 2


def test_corporate_suffix_variant_still_merges():
    entities = [
        _company("OpenAI Inc.", None),
        _company("OpenAI", None),
    ]
    result = resolve_entities(entities)
    assert len(result.resolved_entities) == 1


def test_model_size_variants_do_not_merge():
    """Regression test: different-sized releases of the same model family
    were previously merged by fuzzy/semantic resolution because most other
    tokens matched — exactly the kind of false positive spec section 20
    warns against. Real bug caught during a live pipeline run.
    """
    from src.models.entities import ModelMetadata

    def _model(name: str) -> Entity:
        return Entity(
            id=make_entity_id(EntityType.MODEL, name),
            entity_type=EntityType.MODEL, name=name,
            description="text-generation model on Hugging Face",
            categories=["model"], source=SourceInfo(name="Hugging Face"),
        )

    pairs = [
        ("Qwen/Qwen3-8B", "Qwen/Qwen3-0.6B"),
        ("meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.2-1B-Instruct"),
        ("Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-7B-Instruct"),
        ("cross-encoder/ms-marco-MiniLM-L4-v2", "cross-encoder/ms-marco-MiniLM-L6-v2"),
        ("BAAI/bge-large-en-v1.5", "BAAI/bge-small-en-v1.5"),
    ]
    for name_a, name_b in pairs:
        result = resolve_entities([_model(name_a), _model(name_b)])
        assert len(result.resolved_entities) == 2, f"{name_a} incorrectly merged with {name_b}"


def test_model_variant_tag_does_not_merge():
    """Regression test: a modality/language-variant tag (VL, xlm-) is
    exactly the token that should block a merge, not get lost in fuzzy
    scoring noise."""
    def _model(name: str) -> Entity:
        return Entity(
            id=make_entity_id(EntityType.MODEL, name),
            entity_type=EntityType.MODEL, name=name,
            categories=["model"], source=SourceInfo(name="Hugging Face"),
        )

    result = resolve_entities([
        _model("Qwen/Qwen2.5-VL-7B-Instruct"),
        _model("Qwen/Qwen2.5-7B-Instruct"),
    ])
    assert len(result.resolved_entities) == 2

    result2 = resolve_entities([
        _model("FacebookAI/roberta-base"),
        _model("FacebookAI/xlm-roberta-base"),
    ])
    assert len(result2.resolved_entities) == 2


def test_different_entity_types_never_merge_even_with_same_name():
    company = _company("Claude", "https://anthropic.com/claude")
    model = Entity(
        id=make_entity_id(EntityType.MODEL, "https://huggingface.co/claude"),
        entity_type=EntityType.MODEL,
        name="Claude",
        url="https://huggingface.co/claude",
        categories=["model"],
        source=SourceInfo(name="huggingface"),
    )
    result = resolve_entities([company, model])
    assert len(result.resolved_entities) == 2


def test_merge_preserves_audit_trail_provenance():
    entities = [
        _company("OpenAI", "https://openai.com", source_name="GitHub"),
        _company("OpenAI", "https://openai.com", source_name="Directory"),
    ]
    result = resolve_entities(entities)
    assert len(result.audit_trail) == 1
    record = result.audit_trail[0]
    assert record.confidence == 1.0
    assert record.merged_entity_name == "OpenAI"
