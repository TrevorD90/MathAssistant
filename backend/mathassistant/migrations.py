"""Versioned SQLite schema migrations (spec §10).

Tracked with `PRAGMA user_version`. Migrations are append-only: never edit a
shipped migration; add a new one. Each runs in a transaction, so a failure
leaves the database at the previous version rather than half-migrated.
"""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[str] = [
    # v1 — initial schema
    """
    CREATE TABLE problems (
        id            TEXT PRIMARY KEY,
        title         TEXT NOT NULL,
        problem_latex TEXT NOT NULL,
        level         INTEGER NOT NULL,
        plan_json     TEXT NOT NULL,      -- step plan (includes step results)
        solution_json TEXT NOT NULL,      -- SymPy answer (srepr) or {"kind": "none"}
        state_json    TEXT NOT NULL,      -- engine state: step, phase, attempts, display...
        transcript_json TEXT NOT NULL,    -- last few turns only
        summary       TEXT NOT NULL DEFAULT '',
        status        TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
        tokens_in     INTEGER NOT NULL DEFAULT 0,
        tokens_out    INTEGER NOT NULL DEFAULT 0,
        ai_calls      INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    );
    CREATE INDEX idx_problems_status_updated ON problems (status, updated_at DESC);

    -- Non-secret settings only (provider, model, capability flags). NEVER the API key.
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # v2 — word problems (2026-09-28). Existing rows are math problems.
    """
    ALTER TABLE problems ADD COLUMN problem_kind TEXT NOT NULL DEFAULT 'math'
        CHECK (problem_kind IN ('math', 'words'));
    """,
    # v3 — "Up next": problems read from a worksheet but not started yet (no plan, no AI cost).
    """
    CREATE TABLE queued_problems (
        id           TEXT PRIMARY KEY,
        problem_text TEXT NOT NULL,          -- LaTeX (math) or plain text (words)
        problem_kind TEXT NOT NULL CHECK (problem_kind IN ('math', 'words')),
        label        TEXT NOT NULL DEFAULT '',
        instruction  TEXT NOT NULL DEFAULT '',
        source       TEXT NOT NULL DEFAULT '',
        position     INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT NOT NULL
    );
    CREATE INDEX idx_queued_created ON queued_problems (created_at, position);
    """,
]


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations. Returns the resulting schema version."""
    version = current_version(conn)
    if version > len(MIGRATIONS):
        # Database from a newer app version: don't touch it.
        raise RuntimeError(
            f"database schema v{version} is newer than this app supports (v{len(MIGRATIONS)})"
        )
    for target in range(version + 1, len(MIGRATIONS) + 1):
        sql = MIGRATIONS[target - 1]
        try:
            conn.execute("BEGIN")
            for stmt in (s.strip() for s in sql.split(";")):
                if stmt:
                    conn.execute(stmt)
            conn.execute(f"PRAGMA user_version = {target}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return current_version(conn)
