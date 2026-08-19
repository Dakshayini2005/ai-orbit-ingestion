from src.models.entities import Entity, RepositoryMetadata, SourceInfo, make_entity_id
from src.models.enums import EntityType, RelationshipType
from src.relationships.resolver import build_relationships
from src.relationships.rules import github_owner_develops_repository


def _company(name: str, url: str) -> Entity:
    return Entity(
        id=make_entity_id(EntityType.COMPANY, url),
        entity_type=EntityType.COMPANY, name=name, url=url,
        categories=["company"], source=SourceInfo(name="directory"),
    )


def _repo(name: str, url: str, owner: str) -> Entity:
    return Entity(
        id=make_entity_id(EntityType.REPOSITORY, url),
        entity_type=EntityType.REPOSITORY, name=name, url=url,
        categories=["repository"], source=SourceInfo(name="GitHub"),
        repository_metadata=RepositoryMetadata(owner=owner),
    )


def _task(name: str) -> Entity:
    return Entity(
        id=make_entity_id(EntityType.TASK, name),
        entity_type=EntityType.TASK, name=name,
        categories=["task"], source=SourceInfo(name="directory"),
    )


def test_github_owner_develops_repository_rule_fires_on_name_match():
    company = _company("huggingface", "https://huggingface.co")
    repo = _repo("transformers", "https://github.com/huggingface/transformers", owner="huggingface")
    candidates = github_owner_develops_repository([company, repo])
    assert len(candidates) == 1
    assert candidates[0].source_id == company.id
    assert candidates[0].target_id == repo.id
    assert candidates[0].relationship == RelationshipType.DEVELOPS


def test_github_owner_rule_no_match_when_no_company_entity():
    repo = _repo("transformers", "https://github.com/huggingface/transformers", owner="huggingface")
    candidates = github_owner_develops_repository([repo])
    assert candidates == []


def test_build_relationships_produces_validated_output_only():
    company = _company("huggingface", "https://huggingface.co")
    repo = _repo("transformers", "https://github.com/huggingface/transformers", owner="huggingface")
    summary = build_relationships([company, repo])
    assert len(summary.relationships) == 1
    rel = summary.relationships[0]
    assert rel.source_id == company.id
    assert rel.target_id == repo.id


def test_solves_relationship_extracted_from_description_text():
    tool = Entity(
        id=make_entity_id(EntityType.TOOL, "summarizer"),
        entity_type=EntityType.TOOL, name="Summarizer Pro",
        description="A tool built for text summarization of long documents.",
        categories=["tool"], source=SourceInfo(name="directory"),
    )
    task = _task("Text Summarization")
    summary = build_relationships([tool, task])
    solves_rels = [r for r in summary.relationships if r.relationship == RelationshipType.SOLVES]
    assert len(solves_rels) == 1
    assert solves_rels[0].source_id == tool.id
    assert solves_rels[0].target_id == task.id


def test_no_relationships_built_when_no_signal_present():
    a = _company("Acme", "https://acme.example")
    b = _task("Unrelated Task")
    summary = build_relationships([a, b])
    assert summary.relationships == []
