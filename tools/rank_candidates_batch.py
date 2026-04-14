"""The Ranker's 'answer' tool.

The Ranker doesn't emit free-text rankings — it calls this tool exactly once
per batch with a structured `rankings` array. The tool writes the results
directly to the DB (creating/updating `vulnerability` rows and journal entries)
and returns a short ack so the agent can stop.

This lets us lean on Claude's tool-use JSON validation instead of parsing
loose model output.
"""

from __future__ import annotations

import json
from typing import Any

from db import store as dbstore
from tools.base import tool
from tools.runtime import get_run_context

_ALLOWED_STATUS = {"new", "needs_delve", "low_priority", "false_positive"}


@tool(
    name="rank_candidates_batch",
    description=(
        "REQUIRED: Call this exactly once with a structured `rankings` array to "
        "finish your ranking batch. Every candidate from the user's batch must "
        "appear in `rankings` with an impact, likelihood, status, and 1-2 sentence "
        "rationale. Call no other tool after this."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rankings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "cwe_id": {"type": "string", "pattern": "^CWE-[0-9]+$"},
                        "path": {"type": "string"},
                        "line_start": {"type": "integer", "minimum": 1},
                        "line_end": {"type": "integer", "minimum": 1},
                        "title": {"type": "string"},
                        "impact": {"type": "integer", "minimum": 1, "maximum": 5},
                        "likelihood": {"type": "integer", "minimum": 1, "maximum": 5},
                        "status": {
                            "type": "string",
                            "enum": ["new", "needs_delve", "low_priority", "false_positive"],
                        },
                        "effort_hours": {
                            "type": "number",
                            "minimum": 0.25,
                            "maximum": 16,
                            "description": "Agile-hours guess for the Delver to fully scan the relevant attack surface for this finding. Think 'ideal hours' — 0.5 trivial, 2 typical, 4+ involved, 8+ a full day of tracing.",
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "candidate_id",
                        "cwe_id",
                        "path",
                        "line_start",
                        "line_end",
                        "title",
                        "impact",
                        "likelihood",
                        "status",
                        "effort_hours",
                        "rationale",
                    ],
                },
            }
        },
        "required": ["rankings"],
    },
)
def rank_candidates_batch(rankings: list[dict[str, Any]]) -> str:
    rctx = get_run_context()
    repo_id = _resolve_repo_id(rctx)
    written: list[int] = []
    skipped: list[str] = []

    for r in rankings:
        if r["status"] not in _ALLOWED_STATUS:
            skipped.append(f"{r.get('candidate_id')}:bad_status")
            continue
        priority = int(r["impact"]) * int(r["likelihood"])
        effort_hours = _clamp_effort(r.get("effort_hours"))
        vuln_id = _upsert_vulnerability(
            rctx,
            repo_id=repo_id,
            row=r,
            priority=priority,
            effort_hours=effort_hours,
        )
        dbstore.append_journal(
            rctx.conn,
            vulnerability_id=vuln_id,
            run_id=rctx.run_id,
            agent="ranker",
            action="ranked",
            payload={
                "candidate_id": r["candidate_id"],
                "impact": r["impact"],
                "likelihood": r["likelihood"],
                "priority": priority,
                "effort_hours": effort_hours,
                "status": r["status"],
                "rationale": r["rationale"],
            },
        )
        written.append(vuln_id)

    return json.dumps({"written": len(written), "skipped": skipped})


def _resolve_repo_id(rctx) -> int:
    row = rctx.conn.execute(
        "SELECT id FROM repo WHERE project_id=? LIMIT 1", (rctx.project_id,)
    ).fetchone()
    if not row:
        raise RuntimeError("no repo for project_id=%d" % rctx.project_id)
    return int(row["id"])


def _upsert_vulnerability(
    rctx, *, repo_id: int, row: dict, priority: int, effort_hours: float | None
) -> int:
    conn = rctx.conn
    existing = conn.execute(
        """
        SELECT id FROM vulnerability
        WHERE project_id=? AND repo_id=? AND path=? AND line_start=?
              AND line_end=? AND cwe_id=?
        """,
        (
            rctx.project_id,
            repo_id,
            row["path"],
            int(row["line_start"]),
            int(row["line_end"]),
            row["cwe_id"],
        ),
    ).fetchone()

    status = _rank_to_status(row["status"])
    if existing:
        conn.execute(
            """
            UPDATE vulnerability
            SET title=?, impact=?, likelihood=?, priority=?, effort_hours=?, status=?,
                last_seen_run_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                row["title"],
                int(row["impact"]),
                int(row["likelihood"]),
                priority,
                effort_hours,
                status,
                rctx.run_id,
                existing["id"],
            ),
        )
        return int(existing["id"])

    cur = conn.execute(
        """
        INSERT INTO vulnerability(
            project_id, repo_id, path, line_start, line_end, cwe_id,
            title, short_desc, impact, likelihood, priority, effort_hours, status,
            first_seen_run_id, last_seen_run_id
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rctx.project_id,
            repo_id,
            row["path"],
            int(row["line_start"]),
            int(row["line_end"]),
            row["cwe_id"],
            row["title"],
            row.get("rationale", "")[:400],
            int(row["impact"]),
            int(row["likelihood"]),
            priority,
            effort_hours,
            status,
            rctx.run_id,
            rctx.run_id,
        ),
    )
    return int(cur.lastrowid)


def _clamp_effort(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f < 0.25:
        return 0.25
    if f > 16.0:
        return 16.0
    return round(f, 2)


def _rank_to_status(ranker_status: str) -> str:
    # Ranker vocabulary → persisted vulnerability.status vocabulary.
    # 'new' from ranker just means "freshly ranked, not yet routed" which maps
    # to the DB's 'new' too.
    return {
        "new": "new",
        "needs_delve": "needs_delve",
        "low_priority": "low_priority",
        "false_positive": "false_positive",
    }[ranker_status]
