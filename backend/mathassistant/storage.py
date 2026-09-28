"""SQLite persistence for problems and non-secret settings (spec §10).

One file under the platformdirs data folder, created on first launch. A new
connection per operation keeps this simple and thread-safe for a single-user
local server. The API key is never stored here (N9).
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import migrations
from .paths import db_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ProblemRecord:
    id: str
    title: str
    problem_latex: str
    level: int
    plan: dict
    solution: dict
    state: dict
    transcript: list[dict]
    summary: str = ""
    status: str = "in_progress"
    tokens_in: int = 0
    tokens_out: int = 0
    ai_calls: int = 0
    problem_kind: str = "math"          # "math" (LaTeX) | "words" (word problem text)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @staticmethod
    def new(**kwargs) -> "ProblemRecord":
        return ProblemRecord(id=uuid.uuid4().hex, **kwargs)


class Storage:
    def __init__(self, path: Path | None = None):
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            migrations.migrate(conn)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # isolation_level=None: autocommit; migrations manage their own transaction.
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------ problems

    def save_problem(self, rec: ProblemRecord) -> None:
        """Insert or update (autosave after every turn)."""
        rec.updated_at = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO problems (id, title, problem_latex, level, plan_json, solution_json,
                    state_json, transcript_json, summary, status, tokens_in, tokens_out, ai_calls,
                    problem_kind, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, level=excluded.level, plan_json=excluded.plan_json,
                    solution_json=excluded.solution_json, state_json=excluded.state_json,
                    transcript_json=excluded.transcript_json, summary=excluded.summary,
                    status=excluded.status, tokens_in=excluded.tokens_in,
                    tokens_out=excluded.tokens_out, ai_calls=excluded.ai_calls,
                    updated_at=excluded.updated_at
                """,
                (
                    rec.id, rec.title, rec.problem_latex, rec.level,
                    json.dumps(rec.plan), json.dumps(rec.solution), json.dumps(rec.state),
                    json.dumps(rec.transcript), rec.summary, rec.status,
                    rec.tokens_in, rec.tokens_out, rec.ai_calls, rec.problem_kind, rec.created_at, rec.updated_at,
                ),
            )

    def get_problem(self, problem_id: str) -> ProblemRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM problems WHERE id = ?", (problem_id,)).fetchone()
        return self._row_to_record(row) if row else None

    # ------------------------------------------------------------ up next (queued)

    def add_queued(self, items: list[dict], source: str = "") -> list[str]:
        """Save not-yet-started problems (from a worksheet). Returns their ids."""
        ids: list[str] = []
        now = _now()
        with self._conn() as conn:
            for pos, it in enumerate(items):
                qid = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO queued_problems (id, problem_text, problem_kind, label, instruction, source, "
                    "position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (qid, it["problem_text"], it["problem_kind"], it.get("label", ""),
                     it.get("instruction", ""), source, pos, now),
                )
                ids.append(qid)
        return ids

    def list_queued(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, problem_text, problem_kind, label, instruction, source, created_at "
                "FROM queued_problems ORDER BY created_at, position"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_queued(self, qid: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM queued_problems WHERE id = ?", (qid,)).fetchone()
        return dict(row) if row else None

    def delete_queued(self, qid: str) -> bool:
        with self._conn() as conn:
            return conn.execute("DELETE FROM queued_problems WHERE id = ?", (qid,)).rowcount > 0

    def list_problems(self) -> dict[str, list[dict]]:
        """Summaries for the My problems screen: up next, in progress, completed (newest first)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, title, problem_latex, problem_kind, level, status, created_at, updated_at "
                "FROM problems ORDER BY updated_at DESC"
            ).fetchall()
        out: dict[str, list[dict]] = {"in_progress": [], "completed": []}
        for r in rows:
            out[r["status"]].append(dict(r))
        out["up_next"] = self.list_queued()
        return out

    def delete_problem(self, problem_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM problems WHERE id = ?", (problem_id,))
            return cur.rowcount > 0

    def delete_all_problems(self) -> int:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM problems")
            queued = conn.execute("DELETE FROM queued_problems").rowcount
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            return cur.rowcount + queued

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ProblemRecord:
        return ProblemRecord(
            id=row["id"], title=row["title"], problem_latex=row["problem_latex"],
            level=row["level"], plan=json.loads(row["plan_json"]),
            solution=json.loads(row["solution_json"]), state=json.loads(row["state_json"]),
            transcript=json.loads(row["transcript_json"]), summary=row["summary"],
            status=row["status"], tokens_in=row["tokens_in"], tokens_out=row["tokens_out"],
            ai_calls=row["ai_calls"], problem_kind=row["problem_kind"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------ settings

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        if re.search(r"api_?key|secret|token|password", key, re.I):
            # Guard against accidentally persisting a secret (N9).
            raise ValueError("secrets are not stored in the settings table")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
