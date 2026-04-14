from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(db_path: str | Path) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# ---------- CWE ----------

def upsert_cwe(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    n = 0
    for row in rows:
        conn.execute(
            """
            INSERT INTO cwe(id, name, short_desc, detail, consequences, mitigations, parent_id)
            VALUES(:id, :name, :short_desc, :detail, :consequences, :mitigations, :parent_id)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                short_desc=excluded.short_desc,
                detail=excluded.detail,
                consequences=excluded.consequences,
                mitigations=excluded.mitigations,
                parent_id=excluded.parent_id
            """,
            row,
        )
        n += 1
    return n


def get_cwe(conn: sqlite3.Connection, cwe_id: str) -> dict[str, Any] | None:
    r = conn.execute("SELECT * FROM cwe WHERE id=?", (cwe_id,)).fetchone()
    return dict(r) if r else None


# ---------- Runs ----------

def create_run(conn: sqlite3.Connection, session_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO run(session_id, started_at, status) VALUES(?, CURRENT_TIMESTAMP, 'running')",
        (session_id,),
    )
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    pct_daily: float,
    halted_reason: str | None,
) -> None:
    conn.execute(
        """
        UPDATE run
        SET finished_at=CURRENT_TIMESTAMP, status=?, tokens_in=?, tokens_out=?,
            cost_usd=?, pct_daily_budget_used=?, halted_reason=?
        WHERE id=?
        """,
        (status, tokens_in, tokens_out, cost_usd, pct_daily, halted_reason, run_id),
    )


# ---------- Annotations ----------

def upsert_annotation(
    conn: sqlite3.Connection,
    *,
    repo_id: int,
    path: str,
    summary: str,
    trust_boundary: bool,
    entry_point: bool,
    dataflows: list[str],
    claude_md_path: str | None,
    last_run_id: int | None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO annotation(repo_id, path, claude_md_path, summary,
                               trust_boundary, entry_point, dataflows_json, last_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo_id, path) DO UPDATE SET
            claude_md_path=excluded.claude_md_path,
            summary=excluded.summary,
            trust_boundary=excluded.trust_boundary,
            entry_point=excluded.entry_point,
            dataflows_json=excluded.dataflows_json,
            last_run_id=excluded.last_run_id,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            repo_id,
            path,
            claude_md_path,
            summary,
            1 if trust_boundary else 0,
            1 if entry_point else 0,
            json.dumps(dataflows),
            last_run_id,
        ),
    )
    return int(cur.lastrowid)


# ---------- Journal ----------

def append_journal(
    conn: sqlite3.Connection,
    *,
    vulnerability_id: int | None,
    run_id: int | None,
    agent: str,
    action: str,
    payload: dict[str, Any] | None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO journal_entry(vulnerability_id, run_id, agent, action, payload_json)
        VALUES(?, ?, ?, ?, ?)
        """,
        (vulnerability_id, run_id, agent, action, json.dumps(payload) if payload else None),
    )
    return int(cur.lastrowid)


# ---------- Token ledger ----------

def add_tokens_today(
    conn: sqlite3.Connection, tokens_in: int, tokens_out: int, cost_usd: float
) -> None:
    today = date.today().isoformat()
    conn.execute(
        """
        INSERT INTO token_ledger(day, tokens_in, tokens_out, cost_usd)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(day) DO UPDATE SET
            tokens_in = tokens_in + excluded.tokens_in,
            tokens_out = tokens_out + excluded.tokens_out,
            cost_usd = cost_usd + excluded.cost_usd
        """,
        (today, tokens_in, tokens_out, cost_usd),
    )


def tokens_used_today(conn: sqlite3.Connection) -> int:
    today = date.today().isoformat()
    r = conn.execute(
        "SELECT COALESCE(tokens_in,0)+COALESCE(tokens_out,0) AS t FROM token_ledger WHERE day=?",
        (today,),
    ).fetchone()
    return int(r["t"]) if r else 0


# ---------- Availability ----------

def list_availability_cells(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """Return (day_of_week, hour) tuples for every enabled cell in the general
    weekly pattern. Empty list means nothing scheduled — forecaster will
    treat the agent as idle indefinitely."""
    rows = conn.execute(
        "SELECT day_of_week, hour FROM availability_cell ORDER BY day_of_week, hour"
    ).fetchall()
    return [(int(r["day_of_week"]), int(r["hour"])) for r in rows]


def replace_availability_cells(
    conn: sqlite3.Connection, cells: Iterable[tuple[int, int]]
) -> int:
    """Atomic replace of the general pattern with the caller's cell set.
    The UI sends its full grid on save — we wipe and re-insert so the set is
    always exactly what the user sees."""
    with tx(conn):
        conn.execute("DELETE FROM availability_cell")
        n = 0
        for (dow, hour) in cells:
            if not (0 <= int(dow) <= 6 and 0 <= int(hour) <= 23):
                continue
            conn.execute(
                "INSERT OR IGNORE INTO availability_cell(day_of_week, hour) VALUES(?, ?)",
                (int(dow), int(hour)),
            )
            n += 1
    return n


def list_availability_overrides(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM availability_override ORDER BY start_at"
    ).fetchall()
    return [dict(r) for r in rows]


def add_availability_override(
    conn: sqlite3.Connection,
    *,
    start_at: str,
    end_at: str,
    mode: str,
    note: str | None,
) -> int:
    if mode not in ("available", "blocked"):
        raise ValueError(f"invalid override mode {mode!r}")
    cur = conn.execute(
        """
        INSERT INTO availability_override(start_at, end_at, mode, note)
        VALUES(?, ?, ?, ?)
        """,
        (start_at, end_at, mode, note),
    )
    return int(cur.lastrowid)


def delete_availability_override(conn: sqlite3.Connection, override_id: int) -> None:
    conn.execute("DELETE FROM availability_override WHERE id=?", (int(override_id),))
