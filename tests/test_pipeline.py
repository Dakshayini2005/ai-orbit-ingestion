"""End-to-end pipeline tests, run entirely in --demo mode so they need no
network access or credentials and are fully reproducible in CI.
"""
import pytest

from src.pipeline.orchestrator import run_pipeline


@pytest.fixture(scope="module")
def demo_run():
    return run_pipeline(demo=True)


def test_pipeline_produces_output_files(demo_run):
    from pathlib import Path
    assert Path(demo_run.entities_path).exists()
    assert Path(demo_run.relationships_path).exists()
    assert Path(demo_run.quality_report_path).exists()


def test_pipeline_produces_nonzero_entities(demo_run):
    assert demo_run.quality_report.final_entity_count > 0


def test_pipeline_covers_multiple_entity_types(demo_run):
    types_present = set(demo_run.quality_report.entities_by_type.keys())
    # Demo fixtures span at least these categories across all adapters.
    expected_subset = {"repository", "model", "video", "news", "company", "task"}
    assert expected_subset.issubset(types_present)


def test_pipeline_relationships_reference_valid_entities(demo_run):
    from src.config.settings import DATA_DIR
    from src.utils.helpers import read_json

    entities = read_json(DATA_DIR / "entities.json")
    relationships = read_json(DATA_DIR / "relationships.json")
    entity_ids = {e["id"] for e in entities}

    for rel in relationships:
        assert rel["source_id"] in entity_ids
        assert rel["target_id"] in entity_ids


def test_pipeline_no_duplicate_relationships(demo_run):
    from src.config.settings import DATA_DIR
    from src.utils.helpers import read_json

    relationships = read_json(DATA_DIR / "relationships.json")
    keys = [(r["source_id"], r["relationship"], r["target_id"]) for r in relationships]
    assert len(keys) == len(set(keys))


def test_single_source_run_only_touches_that_source():
    result = run_pipeline(demo=True, only_source="github")
    sources = set(result.quality_report.entities_by_source.keys())
    assert sources == {"GitHub"}
