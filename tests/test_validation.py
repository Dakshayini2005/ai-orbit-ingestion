import pytest
from pydantic import ValidationError

from src.models.entities import Entity, SourceInfo, make_entity_id
from src.models.enums import EntityType, RelationshipType
from src.models.relationships import Relationship
from src.validation.entity_validator import validate_entities, validate_entity
from src.validation.relationship_validator import validate_relationship, validate_relationship_graph


def _entity(name="Valid Tool", url="https://example.com", categories=None) -> Entity:
    return Entity(
        id=make_entity_id(EntityType.TOOL, url or name),
        entity_type=EntityType.TOOL, name=name, url=url,
        categories=categories if categories is not None else ["tool"],
        source=SourceInfo(name="test"),
    )


def test_valid_entity_passes():
    ok, problems = validate_entity(_entity())
    assert ok
    assert problems == []


def test_placeholder_name_rejected():
    ok, problems = validate_entity(_entity(name="Unknown"))
    assert not ok
    assert any("name" in p for p in problems)


def test_invalid_url_rejected():
    ok, problems = validate_entity(_entity(url="not-a-url"))
    assert not ok


def test_none_url_is_allowed_optional_field():
    ok, problems = validate_entity(_entity(url=None))
    assert ok


def test_missing_categories_rejected():
    ok, problems = validate_entity(_entity(categories=[]))
    assert not ok


def test_blank_name_rejected_at_pydantic_layer():
    with pytest.raises(ValidationError):
        Entity(
            id=make_entity_id(EntityType.TOOL, "x"),
            entity_type=EntityType.TOOL, name="   ",
            categories=["tool"], source=SourceInfo(name="test"),
        )


def test_validate_entities_splits_valid_and_invalid():
    good = _entity(name="Good Tool")
    bad = _entity(name="N/A")
    valid, invalid = validate_entities([good, bad])
    assert good in valid
    assert bad.id in invalid


def test_relationship_rejects_dangling_source():
    company = _entity(name="Acme Co")
    rel = Relationship(
        source_id="does-not-exist", relationship=RelationshipType.DEVELOPS,
        target_id=company.id, confidence=0.9, source=SourceInfo(name="test"),
    )
    ok, reason = validate_relationship(rel, {company.id: company})
    assert not ok
    assert "dangling source" in reason


def test_relationship_rejects_incompatible_types():
    a = _entity(name="Tool A", url="https://example.com/a")
    b = _entity(name="Tool B", url="https://example.com/b")
    rel = Relationship(
        source_id=a.id, relationship=RelationshipType.DEVELOPS,
        target_id=b.id, confidence=0.9, source=SourceInfo(name="test"),
    )
    ok, reason = validate_relationship(rel, {a.id: a, b.id: b})
    assert not ok
    assert "incompatible" in reason


def test_relationship_graph_dedupes_exact_duplicates():
    a = _entity(name="Tool A", url="https://example.com/a")
    b = _entity(name="Tool B", url="https://example.com/b")
    rel = Relationship(
        source_id=a.id, relationship=RelationshipType.DEVELOPS,
        target_id=b.id, confidence=0.9, source=SourceInfo(name="test"),
    )
    deduped, notes = validate_relationship_graph([rel, rel])
    assert len(deduped) == 1
    assert len(notes) == 1
