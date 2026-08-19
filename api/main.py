"""Thin API layer around the AI Orbit ingestion pipeline.

The pipeline itself (src/) is a CLI/library — this module is the ONLY thing
that turns it into something deployable behind a public URL. It doesn't
duplicate any pipeline logic; it just calls src.pipeline.orchestrator and
serves the resulting JSON files.

No authentication — every route is intentionally open, per deployment
requirements (reviewer access with no login/signup).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config.settings import DATA_DIR
from src.pipeline.orchestrator import run_pipeline
from src.utils.helpers import read_json
from src.utils.logging import get_logger

logger = get_logger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


app = FastAPI(
    title="AI Orbit Data Ingestion Pipeline",
    description=(
        "API-first ingestion pipeline for the AI ecosystem: GitHub, Hugging "
        "Face, YouTube, RSS/news, and curated directories, merged through "
        "multi-stage entity resolution into entities.json + "
        "relationships.json. See /docs for interactive endpoint docs."
    ),
    version="1.0.0",
)

# Open CORS — this is a public, read-only data API with no auth, so there is
# no session/credential surface for CORS to protect.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_run_lock = threading.Lock()
_run_in_progress = False


def _outputs_exist() -> bool:
    return (DATA_DIR / "entities.json").exists()


def _run_pipeline_background(demo: bool, only_source: Optional[str]) -> None:
    global _run_in_progress
    try:
        run_pipeline(demo=demo, only_source=only_source)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"api: background pipeline run failed: {exc}")
    finally:
        with _run_lock:
            _run_in_progress = False


@app.on_event("startup")
def _seed_on_startup() -> None:
    """If this is a fresh deployment with no data yet, populate it once so
    the API isn't empty on first load. Tries live sources first (GitHub/HF/
    RSS all work without credentials); each source degrades to its own demo
    fixtures individually if the deployment environment blocks outbound
    network access, so this never crashes the app on startup.
    """
    if _outputs_exist():
        return
    logger.info("api: no existing output found, seeding initial data on startup")
    try:
        run_pipeline(demo=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"api: live seed failed ({exc}), falling back to demo mode")
        try:
            run_pipeline(demo=True)
        except Exception as exc2:  # noqa: BLE001
            logger.error(f"api: demo seed also failed: {exc2}")


@app.get("/", response_class=HTMLResponse)
def root(request: Request) -> str:
    if not _outputs_exist():
        return templates.TemplateResponse(request, "dashboard.html", {"has_data": False})

    entities = read_json(DATA_DIR / "entities.json")
    relationships = read_json(DATA_DIR / "relationships.json")
    report = read_json(DATA_DIR / "quality_report.json")

    entities_by_type = sorted(report.get("entities_by_type", {}).items(), key=lambda kv: -kv[1])
    entities_by_source = sorted(report.get("entities_by_source", {}).items(), key=lambda kv: -kv[1])
    max_type_count = max((c for _, c in entities_by_type), default=1)
    max_source_count = max((c for _, c in entities_by_source), default=1)
    entity_names = {e["id"]: e["name"] for e in entities}

    return templates.TemplateResponse(request, "dashboard.html", {
        "has_data": True,
        "entities": entities,
        "relationships": relationships,
        "report": report,
        "entities_by_type": entities_by_type,
        "entities_by_source": entities_by_source,
        "max_type_count": max_type_count,
        "max_source_count": max_source_count,
        "entity_names": entity_names,
        "source_run_notes": report.get("source_run_notes", {}),
    })


@app.get("/status")
def status() -> dict:
    return {
        "data_available": _outputs_exist(),
        "run_in_progress": _run_in_progress,
    }


@app.get("/entities")
def get_entities(
    entity_type: Optional[str] = Query(None, description="Filter by entity_type, e.g. 'model' or 'repository'"),
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    path = DATA_DIR / "entities.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No entities.json yet — POST /run first (or wait for startup seeding).")
    data = read_json(path)
    if entity_type:
        data = [e for e in data if e.get("entity_type") == entity_type]
    return {"count": len(data), "entities": data[:limit]}


@app.get("/relationships")
def get_relationships(limit: int = Query(500, ge=1, le=2000)) -> dict:
    path = DATA_DIR / "relationships.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No relationships.json yet — POST /run first.")
    data = read_json(path)
    return {"count": len(data), "relationships": data[:limit]}


@app.get("/quality-report")
def get_quality_report() -> dict:
    path = DATA_DIR / "quality_report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No quality_report.json yet — POST /run first.")
    return read_json(path)


@app.post("/run")
def trigger_run(
    demo: bool = Query(False, description="False (default) = live API sources, falling back to demo per-source only on failure. True = force deterministic fixture data for every source."),
    source: Optional[str] = Query(None, description="Run a single source only: github|huggingface|youtube|rss|directory"),
) -> dict:
    """Triggers a pipeline run in the background and returns immediately.
    Poll /status or re-check /entities once run_in_progress is false.
    Defaults to live sources (demo=False) so this never silently overwrites
    real data with fixtures — pass ?demo=true explicitly if you want that.
    """
    global _run_in_progress
    with _run_lock:
        if _run_in_progress:
            return {"started": False, "message": "A pipeline run is already in progress."}
        _run_in_progress = True

    thread = threading.Thread(target=_run_pipeline_background, args=(demo, source), daemon=True)
    thread.start()
    return {"started": True, "demo": demo, "source": source, "message": "Pipeline running in background — check /status."}
