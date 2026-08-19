from src.classification.classifier import classify_entity, classify_entities
from src.models.entities import Entity, SourceInfo, make_entity_id
from src.models.enums import EntityType


def _entity(name: str, description: str, entity_type: EntityType = EntityType.TOOL) -> Entity:
    return Entity(
        id=make_entity_id(entity_type, name),
        entity_type=entity_type,
        name=name,
        description=description,
        categories=[],
        source=SourceInfo(name="test"),
    )


def test_entity_type_category_always_present():
    e = classify_entity(_entity("Some Tool", "A generic tool."))
    assert "tool" in e.categories


def test_keyword_rule_adds_agent_category():
    e = classify_entity(_entity("AutoAgent", "An autonomous AI agent framework."))
    assert "ai-agent" in e.categories


def test_keyword_rule_adds_image_generation_category():
    e = classify_entity(_entity("PixelForge", "A diffusion-based text-to-image tool."))
    assert "image-generation" in e.categories


def test_keyword_rule_adds_robotics_category():
    e = classify_entity(_entity("Atlas", "A humanoid robot platform."), )
    assert "robotics" in e.categories


def test_classification_is_deterministic():
    e1 = classify_entity(_entity("RAGTool", "A retrieval-augmented generation tool."))
    e2 = classify_entity(_entity("RAGTool", "A retrieval-augmented generation tool."))
    assert set(e1.categories) == set(e2.categories)


def test_classify_entities_processes_a_list():
    entities = [_entity("A", "an assistant"), _entity("B", "a chat tool")]
    result = classify_entities(entities)
    assert len(result) == 2
    assert all("tool" in e.categories for e in result)
