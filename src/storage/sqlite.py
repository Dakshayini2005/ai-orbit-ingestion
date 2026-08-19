"""Lightweight SQLite staging/cache layer (spec section 27).

Deliberately minimal: a handful of tables for raw records, normalized
entities, relationship candidates, and run history — enough to make
`--resume` meaningful and give post-hoc debugging a queryable trail, without
turning this into an ORM-backed application.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.config.settings import SQLITE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS run_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    mode TEXT NOT NULL,
    final_entity_count INTEGER,
    relationship_count INTEGER
);

CREATE TABLE IF NOT EXISTS source_fetch_status (
    run_id INTEGER,
    source TEXT NOT NULL,
    discovered_count INTEGER,
    entity_count INTEGER,
    used_demo_fallback INTEGER,
    succeeded INTEGER,
    errors TEXT,
    FOREIGN KEY (run_id) REFERENCES run_history (id)
);

CREATE TABLE IF NOT EXISTS normalized_entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationship_candidates (
    source_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    target_id TEXT NOT NULL,
    confidence REAL,
    accepted INTEGER,
    reason TEXT
);
"""


@contextmanager
def get_connection(db_path: Path = SQLITE_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def start_run(conn: sqlite3.Connection, mode: str) -> int:
    cur = conn.execute(
        "INSERT INTO run_history (started_at, mode) VALUES (?, ?)",
        (datetime.now(timezone.utc).isoformat(), mode),
    )
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, final_entity_count: int, relationship_count: int) -> None:
    conn.execute(
        "UPDATE run_history SET finished_at = ?, final_entity_count = ?, relationship_count = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), final_entity_count, relationship_count, run_id),
    )


def record_source_status(conn: sqlite3.Connection, run_id: int, source: str, discovered: int, entity_count: int,
                          used_demo_fallback: bool, succeeded: bool, errors: list[str]) -> None:
    conn.execute(
        "INSERT INTO source_fetch_status (run_id, source, discovered_count, entity_count, used_demo_fallback, succeeded, errors) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_id, source, discovered, entity_count, int(used_demo_fallback), int(succeeded), json.dumps(errors)),
    )


def upsert_entities(conn: sqlite3.Connection, entities: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT INTO normalized_entities (id, entity_type, name, payload, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
        [(e["id"], e["entity_type"], e["name"], json.dumps(e), now) for e in entities],
    )


def record_relationship_candidates(conn: sqlite3.Connection, candidates: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO relationship_candidates (source_id, relationship, target_id, confidence, accepted, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(c["source_id"], c["relationship"], c["target_id"], c["confidence"], int(c["accepted"]), c.get("reason")) for c in candidates],
    )


def load_cached_entities(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT payload FROM normalized_entities").fetchall()
    return [json.loads(r[0]) for r in rows]
