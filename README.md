# AI Orbit Data Ingestion Pipeline

A modular, API-first Python pipeline that discovers, cleans, normalizes,
deduplicates, classifies, and connects entities across the AI ecosystem —
tools, models, repositories, companies, MCP servers, news, videos, robots,
devices, personal assistants, creative-generation tools, tasks, and curated
collections — into two artifacts: `data/entities.json` and
`data/relationships.json`, backed by a `data/quality_report.json` you can
audit.

```
Discovery → Extraction → Cleaning → Normalization → Entity Resolution
    + Deduplication → Classification → Enrichment → Relationship Engine
    → Validation → entities.json + relationships.json
```

## Quick start

```bash
pip install -r requirements.txt
python run.py --demo
```

That's it — `--demo` runs the entire pipeline against deterministic,
clearly-marked fixture data and needs no API credentials. Output lands in
`data/entities.json`, `data/relationships.json`, and
`data/quality_report.json`, plus a console summary.

## Running against live sources

Copy `.env.example` to `.env` and fill in whichever credentials you have —
**all of them are optional**:

```bash
cp .env.example .env
# edit .env: GITHUB_TOKEN, HUGGINGFACE_TOKEN, YOUTUBE_API_KEY
python run.py
```

Per-source behavior when a credential is missing or a live call fails:

| Source | Requires credential? | Behavior without it / on failure |
|---|---|---|
| GitHub | No (unauthenticated works, rate-limited to 60 req/hr) | Falls back to demo fixtures on repeated failure |
| Hugging Face | No (public reads) | Falls back to demo fixtures on repeated failure |
| YouTube | **Yes** (`YOUTUBE_API_KEY`) | Falls back to demo fixtures — this is the source most likely to run in fallback mode |
| RSS | No | Falls back to demo fixtures only if *every* configured feed fails |
| AI Directories | No live source exists (see [Known limitations](#known-limitations)) | Always uses a curated, hand-maintained fixture set |
| Official Sites | No | Used only for optional enrichment (`--live-enrichment`); never a hard dependency |

Demo/fallback data is always clearly marked (`used_demo_fallback: true` in
the quality report, `"source": {"name": "... (curated)"}` in entity
records) — it is never presented as if it came from a live API call.

## CLI

```bash
python run.py                    # full pipeline; live where possible, demo fallback per-source
python run.py --demo             # full pipeline, demo fixtures for every source
python run.py --source github    # run one adapter only (github|huggingface|youtube|rss|directory)
python run.py --resume           # reuse SQLite-cached normalized entities
python run.py --validate         # re-validate the last-written data/entities.json and exit
python run.py --live-enrichment  # allow the enrichment stage to make outbound HTTP requests
```

## Architecture

Every source implements the same interface
(`src/discovery/base.py::SourceAdapter`: `discover()` → `fetch()` →
`normalize()`), so the pipeline orchestrator (`src/pipeline/orchestrator.py`)
never contains source-specific branching, and adding a new source means
adding one new file. Each stage after extraction is an independently
importable, independently testable module:

```
src/
├── config/settings.py         environment-driven configuration, all credentials optional
├── models/                    Pydantic Entity + Relationship schemas, shared enums
├── discovery/                 one adapter per source (github, huggingface, youtube, rss, directories, official_sites)
├── extraction/extractor.py    runs adapters with per-source exception isolation, persists raw responses
├── cleaning/cleaner.py        HTML/unicode/boilerplate cleanup, preserves technical terms
├── normalization/             URL normalization, name normalization, category normalization
├── resolution/                multi-stage entity resolution + cross-source deduplication
├── classification/            hybrid rule/keyword classification
├── enrichment/enricher.py     opt-in official-site verification pass (companies only)
├── relationships/             deterministic rules + text extraction + validated resolver
├── validation/                entity + relationship + graph-consistency checks, quality report
├── storage/sqlite.py          staging/cache layer for resumability and debugging
├── pipeline/orchestrator.py   the only module that knows the full stage order
└── utils/                     logging, retry/backoff, small helpers
```

### Entity IDs are deterministic

`make_entity_id(entity_type, canonical_url_or_name)` uses `uuid5` over a
fixed namespace, so the same underlying entity gets the same ID on every
run — verified by an equality check between two full `--demo` runs in
this repo's test/manual verification. This is what makes `--resume` and
stable relationship references possible.

### Entity resolution (the core of deduplication)

Runs in priority order per candidate pair, **only ever comparing entities
of the same `entity_type`**:

1. Exact canonical URL match → confidence `1.00`
2. Exact normalized name match → confidence `0.95`
3. Alias match → confidence `0.92`
4. Fuzzy match (RapidFuzz token-sort-ratio ≥ configurable threshold) → confidence `0.88`
5. Semantic similarity (token-overlap proxy, name-gated — see note below) → confidence `0.80`

Matches below `RESOLUTION_CONFIDENCE_FLOOR` (default `0.80`) are never
auto-merged. Every merge is recorded in an audit trail
(`MergeAuditRecord`: canonical id, merged entity, original/matched names,
source records, confidence, reason) — this is real entity resolution, not
`drop_duplicates()`.

**Note on stage 5:** the spec makes embeddings *optional* and explicitly
says not to require an LLM for every comparison. Rather than add a
heavyweight embedding dependency, semantic similarity here is a
name-token-overlap proxy, and — after an early bug where two HuggingFace
models with near-identical boilerplate descriptions ("text-generation
model on Hugging Face") were incorrectly merged — description overlap
only contributes if name tokens already overlap at all. This keeps stage 5
conservative, as a last-resort signal should be.

### Relationship extraction

`DEVELOPS`, `SOLVES`, `INTEGRATES_WITH`, `RUNS` — built from deterministic
rules (GitHub repo owner ↔ Company name; HuggingFace model provider ↔
Company name; MCP server description ↔ Tool name; Device/Robot description
↔ Model name) plus one text-extraction pass (Task name appearing in a
Tool/Model's description). **Every** candidate relationship — regardless
of which stage produced it — passes through
`validation/relationship_validator.py` (source/target exist, type pair is
semantically valid, confidence in range, provenance present, no
disallowed self-links) before it can reach `relationships.json`.

LLM-assisted extraction (`relationships/extractor.py::extract_relationships_llm_assisted`)
is a documented, intentional no-op in this build — see the docstring
there for why, and how it would be wired in (strict structured output,
then the *same* validation path as everything else — never a direct write).

## Testing

```bash
pytest -q
```

57 tests across cleaning, URL/name normalization, entity resolution,
deduplication, classification, relationships, validation, and a full
end-to-end pipeline run in `--demo` mode (`tests/test_pipeline.py`) — no
network access or credentials required for the suite to pass.

## Live API deployment

A thin FastAPI wrapper (`api/main.py`) exposes the pipeline's output over
HTTP — no login/signup required for any route:

| Route | What it does |
|---|---|
| `GET /` | Simple status page with links to everything below |
| `GET /entities` | All collected entities (optional `?entity_type=model` filter) |
| `GET /relationships` | All relationships |
| `GET /quality-report` | The quality report as JSON |
| `GET /status` | Whether data exists / a run is in progress |
| `POST /run?demo=true` | Triggers a pipeline run in the background |
| `GET /docs` | Interactive Swagger UI (auto-generated by FastAPI) |

Run it locally:
```bash
uvicorn api.main:app --reload
```
then open `http://localhost:8000`.

On first startup with no existing `data/entities.json`, the API
automatically seeds itself by running the pipeline once (live sources first,
falling back to `--demo` if the deployment environment blocks outbound
network access) — so a fresh deployment isn't empty on first load.

### Deploying to Render (free, no login required for reviewers)

1. Push this repo to GitHub (see below).
2. Go to [render.com](https://render.com) → New → Web Service → connect
   the repo. Render auto-detects `render.yaml`, or set manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
3. Deploy. Render gives you a public URL like
   `https://ai-orbit-ingestion.onrender.com` — share that as the live
   deployment URL. No account/login is needed to view it; only to deploy it.

(`Procfile` is included too, for Railway or any Heroku-style platform.)

## Pushing to GitHub

```bash
git init
git add .
git commit -m "Initial commit: AI Orbit data ingestion pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ai-orbit-ingestion.git
git push -u origin main
```

`.gitignore` already excludes `.env`, generated `data/*.json`, and
`__pycache__/` — only source code and `.env.example` get pushed.

## Known limitations

- **AI directories**: there is no single standardized, broadly-accessible
  free "AI directory API." `src/discovery/directories.py` documents this
  explicitly and always uses a curated, hand-maintained fixture set for
  categories that GitHub/HuggingFace/YouTube/RSS can't naturally surface
  (companies, tasks, robots, devices, personal assistants, creative
  tools, collections, product-level MCP listings). This is deliberate
  graceful degradation, not a fallback from a failed live call.
- **Official sites**: enrichment fetches are opt-in (`--live-enrichment`)
  and scoped to a single respectful GET per already-known company URL —
  no crawling, no link-following.
- **LLM-assisted classification/relationship extraction**: both hybrid
  systems reserve an LLM-assisted stage for genuinely ambiguous cases, but
  at this dataset's scale the deterministic + rule/text stages cover the
  required categories and relationship types, so the LLM stages are
  documented no-ops rather than live integrations with nothing forcing
  their use.
- **Record volume**: the target is ~250–300 *high-quality* records: with
  live credentials for all three APIs and the tunable
  `*_MAX_*` settings in `.env.example` raised, the pipeline comfortably
  reaches that range; the bundled demo fixtures are intentionally smaller
  (~60 records) so `--demo` runs are fast and easy to inspect by hand.

## License

MIT — see `LICENSE`.
