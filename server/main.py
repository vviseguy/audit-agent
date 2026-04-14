"""FastAPI host for the audit agent PWA.

Runs on the home box alongside the Next.js dev server and the APScheduler.
The PWA reads SQLite directly for fast grid rendering, but mutations
(queue a session, validate a token, promote drafts, override a status)
always go through these endpoints so we have one place to enforce policy.

The server is intentionally small: it is a thin layer over `db.store`,
`server.scheduler`, `gh.token_validator`, and `gh.promote`. No business
logic lives here — just request validation and JSON marshalling.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import store as dbstore
from gh import promote as promote_mod
from gh import token_validator
from server import forecast as forecast_mod
from server.scheduler import SessionScheduler, queue_session

log = logging.getLogger(__name__)


CONFIG_PATH = Path(os.environ.get("AUDIT_CONFIG", "config.yaml"))


def _load_cfg() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _conn():
    return dbstore.connect(_load_cfg()["paths"]["db"])


# ---------- lifespan: start/stop the scheduler ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = _load_cfg()
    log_dir = Path("data/logs")
    scheduler = SessionScheduler(cfg, log_dir=log_dir, tick_seconds=10)
    scheduler.start()
    app.state.scheduler = scheduler
    app.state.cfg = cfg
    log.info("server started")
    try:
        yield
    finally:
        scheduler.shutdown()
        log.info("server stopped")


app = FastAPI(title="audit-agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- schemas ----------

class QueueSessionBody(BaseModel):
    project_id: int
    type: str = Field(pattern="^(understand|rank|delve|full)$")
    risk_lens: str = Field(pattern="^(high_impact|high_likelihood|ui_visible|balanced|custom)$")
    interest_prompt: str | None = None
    scheduled_for: datetime
    recurrence_cron: str | None = None
    session_pct_cap: float = 30.0
    budget_hours: float | None = None


class StatusOverrideBody(BaseModel):
    status: str = Field(
        pattern="^(new|needs_delve|low_priority|false_positive|delved|draft_issue|issue_sent|closed|ignored)$"
    )
    note: str | None = None


class PromoteBody(BaseModel):
    project_id: int
    draft_issue_ids: list[int]
    approved_by: str


class AvailabilityCellsBody(BaseModel):
    cells: list[list[int]]  # [[day_of_week, hour], ...]


class AvailabilityOverrideBody(BaseModel):
    start_at: datetime
    end_at: datetime
    mode: str = Field(pattern="^(available|blocked)$")
    note: str | None = None


# ---------- reads ----------

@app.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM vulnerability v WHERE v.project_id=p.id) AS vuln_total,
               (SELECT COUNT(*) FROM vulnerability v WHERE v.project_id=p.id AND v.status='needs_delve') AS vuln_needs_delve,
               (SELECT COUNT(*) FROM vulnerability v WHERE v.project_id=p.id AND v.status='issue_sent') AS vuln_issue_sent,
               (SELECT COALESCE(SUM(v.effort_hours), 0) FROM vulnerability v
                  WHERE v.project_id=p.id AND v.status='needs_delve') AS delve_hours_remaining,
               (SELECT MIN(scheduled_for) FROM session s WHERE s.project_id=p.id AND s.status='queued') AS next_scheduled,
               (SELECT COUNT(*) FROM draft_issue d WHERE d.project_id=p.id AND d.status='draft') AS draft_count
        FROM project p
        ORDER BY p.name
        """
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["read_token"] = _load_token_brief(conn, d.get("read_token_id"))
        d["issues_token"] = _load_token_brief(conn, d.get("issues_token_id"))
        out.append(d)
    return out


def _load_token_brief(conn: sqlite3.Connection, token_id: int | None) -> dict[str, Any] | None:
    if not token_id:
        return None
    t = conn.execute(
        "SELECT id, label, scope, validated_at, validation_result FROM github_token WHERE id=?",
        (token_id,),
    ).fetchone()
    return dict(t) if t else None


@app.get("/projects/{project_id}")
def get_project(project_id: int) -> dict[str, Any]:
    conn = _conn()
    row = conn.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, "project not found")
    out = dict(row)
    forecast = conn.execute(
        """
        SELECT COUNT(*) AS pending_count,
               COALESCE(SUM(effort_hours), 0) AS delve_hours_remaining,
               COALESCE(AVG(effort_hours), 0) AS avg_hours_per_finding
        FROM vulnerability
        WHERE project_id=? AND status='needs_delve'
        """,
        (project_id,),
    ).fetchone()
    out["forecast"] = {
        "pending_count": int(forecast["pending_count"] or 0),
        "delve_hours_remaining": round(float(forecast["delve_hours_remaining"] or 0), 2),
        "avg_hours_per_finding": round(float(forecast["avg_hours_per_finding"] or 0), 2),
    }
    out["read_token"] = _load_token_brief(conn, row["read_token_id"])
    out["issues_token"] = _load_token_brief(conn, row["issues_token_id"])
    out["draft_count"] = int(
        conn.execute(
            "SELECT COUNT(*) FROM draft_issue WHERE project_id=? AND status='draft'",
            (project_id,),
        ).fetchone()[0]
    )
    return out


class CreateRepoBody(BaseModel):
    url: str = Field(min_length=1)
    branch: str = "main"


class CreateProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    default_risk_lens: str = Field(
        default="balanced",
        pattern="^(high_impact|high_likelihood|ui_visible|balanced|custom)$",
    )
    daily_token_budget: int = Field(default=2_000_000, ge=0)
    per_session_pct_cap: float = Field(default=30.0, ge=0, le=100)
    create_issues: bool = False
    read_token_id: int | None = None
    issues_token_id: int | None = None
    repos: list[CreateRepoBody] = Field(default_factory=list)


class ProjectPatchBody(BaseModel):
    default_risk_lens: str | None = None
    daily_token_budget: int | None = None
    per_session_pct_cap: float | None = None
    create_issues: int | None = None
    # Use 0 to explicitly unset a token link; any positive int binds the
    # project to that github_token row. None leaves the field unchanged.
    read_token_id: int | None = None
    issues_token_id: int | None = None


_PROJECT_PATCH_FIELDS = (
    "default_risk_lens",
    "daily_token_budget",
    "per_session_pct_cap",
    "create_issues",
    "read_token_id",
    "issues_token_id",
)


@app.post("/projects")
def create_project(body: CreateProjectBody) -> dict[str, Any]:
    # Parse all repo URLs before touching the DB so a bad URL can't leave
    # an orphaned project row behind (sqlite connection is autocommit).
    parsed_repos = [
        (*_parse_github_url(r.url), r.url, r.branch) for r in body.repos
    ]
    conn = _conn()
    existing = conn.execute(
        "SELECT id FROM project WHERE name=?", (body.name,)
    ).fetchone()
    if existing:
        raise HTTPException(409, f"a project named {body.name!r} already exists")
    cur = conn.execute(
        """
        INSERT INTO project(
            name, default_risk_lens, daily_token_budget, per_session_pct_cap,
            create_issues, read_token_id, issues_token_id
        ) VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            body.name,
            body.default_risk_lens,
            body.daily_token_budget,
            body.per_session_pct_cap,
            1 if body.create_issues else 0,
            body.read_token_id,
            body.issues_token_id,
        ),
    )
    project_id = int(cur.lastrowid)
    for owner, name, url, branch in parsed_repos:
        conn.execute(
            """
            INSERT INTO repo(project_id, url, owner, name, branch)
            VALUES(?, ?, ?, ?, ?)
            """,
            (project_id, url, owner, name, branch),
        )
    return {"id": project_id, "name": body.name}


_GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def _parse_github_url(url: str) -> tuple[str, str]:
    m = _GITHUB_URL_RE.match(url.strip())
    if not m:
        raise HTTPException(
            400,
            f"could not parse owner/name from GitHub URL: {url!r}",
        )
    return m.group(1), m.group(2)


@app.delete("/projects/{project_id}")
def delete_project(project_id: int) -> dict[str, Any]:
    conn = _conn()
    row = conn.execute(
        "SELECT id, name FROM project WHERE id=?", (project_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "project not found")
    # Cascades to repo, session, run, vulnerability, annotation,
    # draft_issue, and journal_entry via FK ON DELETE CASCADE.
    conn.execute("DELETE FROM project WHERE id=?", (project_id,))
    return {"ok": True, "deleted_id": project_id, "deleted_name": row["name"]}


@app.patch("/projects/{project_id}")
def patch_project(project_id: int, body: ProjectPatchBody) -> dict[str, Any]:
    conn = _conn()
    existing = conn.execute("SELECT id FROM project WHERE id=?", (project_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "project not found")
    updates: list[str] = []
    values: list[Any] = []
    for field in _PROJECT_PATCH_FIELDS:
        val = getattr(body, field)
        if val is None:
            continue
        if field in ("read_token_id", "issues_token_id") and val == 0:
            updates.append(f"{field}=NULL")
            continue
        updates.append(f"{field}=?")
        values.append(val)
    if not updates:
        return {"ok": True, "changed": 0}
    updates.append("updated_at=CURRENT_TIMESTAMP")
    values.append(project_id)
    conn.execute(f"UPDATE project SET {', '.join(updates)} WHERE id=?", values)
    conn.commit()
    return {"ok": True, "changed": len(updates) - 1}


@app.get("/projects/{project_id}/vulnerabilities")
def list_vulnerabilities(project_id: int) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT v.*, r.owner AS repo_owner, r.name AS repo_name
        FROM vulnerability v JOIN repo r ON r.id = v.repo_id
        WHERE v.project_id=?
        ORDER BY v.priority DESC, v.id ASC
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/vulnerabilities/{vuln_id}")
def get_vulnerability(vuln_id: int) -> dict[str, Any]:
    conn = _conn()
    row = conn.execute("SELECT * FROM vulnerability WHERE id=?", (vuln_id,)).fetchone()
    if not row:
        raise HTTPException(404, "vulnerability not found")
    out = dict(row)
    out["journal"] = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM journal_entry WHERE vulnerability_id=? ORDER BY created_at ASC",
            (vuln_id,),
        ).fetchall()
    ]
    out["draft_issue"] = None
    draft = conn.execute(
        "SELECT * FROM draft_issue WHERE vulnerability_id=? ORDER BY id DESC LIMIT 1",
        (vuln_id,),
    ).fetchone()
    if draft:
        out["draft_issue"] = dict(draft)
    return out


@app.get("/projects/{project_id}/journal")
def project_journal(project_id: int, limit: int = 200) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT j.*, v.title AS vuln_title
        FROM journal_entry j
        LEFT JOIN vulnerability v ON v.id = j.vulnerability_id
        WHERE v.project_id=? OR j.vulnerability_id IS NULL
        ORDER BY j.created_at DESC
        LIMIT ?
        """,
        (project_id, min(limit, 1000)),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/projects/{project_id}/draft_issues")
def list_drafts(project_id: int) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT d.*, v.cwe_id AS cwe_id, v.path AS vuln_path
        FROM draft_issue d
        LEFT JOIN vulnerability v ON v.id = d.vulnerability_id
        WHERE d.project_id=? AND d.status='draft'
        ORDER BY d.updated_at DESC
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/sessions")
def list_sessions(project_id: int | None = None) -> list[dict[str, Any]]:
    conn = _conn()
    if project_id is None:
        rows = conn.execute(
            "SELECT * FROM session ORDER BY scheduled_for DESC LIMIT 200"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM session WHERE project_id=? ORDER BY scheduled_for DESC LIMIT 200",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/runs")
def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM run ORDER BY started_at DESC LIMIT ?",
        (min(limit, 500),),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/tokens")
def list_tokens() -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """
        SELECT t.id, t.label, t.scope, t.validated_at, t.validation_result,
               (SELECT GROUP_CONCAT(p.name, ', ')
                  FROM project p
                 WHERE p.read_token_id = t.id OR p.issues_token_id = t.id) AS projects
        FROM github_token t
        ORDER BY t.id
        """
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/config")
def get_config() -> dict[str, Any]:
    cfg = _load_cfg()
    # Only return non-secret keys so the Settings page can render them.
    return {
        "budgets": cfg.get("budgets", {}),
        "concurrency": cfg.get("concurrency", {}),
        "paths": {k: v for k, v in cfg.get("paths", {}).items() if "key" not in k},
        "scheduler": cfg.get("scheduler", {}),
    }


@app.get("/budget/today")
def budget_today() -> dict[str, Any]:
    conn = _conn()
    used = dbstore.tokens_used_today(conn)
    cfg = _load_cfg()
    daily = int(cfg["budgets"]["daily_token_budget"])
    return {
        "tokens_used_today": used,
        "daily_token_budget": daily,
        "pct": round(100.0 * used / daily, 2) if daily else 0.0,
    }


# ---------- availability + queue forecast ----------

@app.get("/availability")
def get_availability() -> dict[str, Any]:
    conn = _conn()
    cells = dbstore.list_availability_cells(conn)
    overrides = dbstore.list_availability_overrides(conn)
    return {
        "cells": [[dow, hour] for (dow, hour) in cells],
        "overrides": overrides,
    }


@app.post("/availability/cells")
def post_availability_cells(body: AvailabilityCellsBody) -> dict[str, Any]:
    conn = _conn()
    tuples: list[tuple[int, int]] = []
    for pair in body.cells:
        if len(pair) != 2:
            raise HTTPException(400, f"cell {pair!r} must be [dow, hour]")
        tuples.append((int(pair[0]), int(pair[1])))
    n = dbstore.replace_availability_cells(conn, tuples)
    return {"ok": True, "saved": n}


@app.post("/availability/overrides")
def post_availability_override(body: AvailabilityOverrideBody) -> dict[str, Any]:
    if body.end_at <= body.start_at:
        raise HTTPException(400, "end_at must be after start_at")
    conn = _conn()
    oid = dbstore.add_availability_override(
        conn,
        start_at=body.start_at.isoformat(sep=" "),
        end_at=body.end_at.isoformat(sep=" "),
        mode=body.mode,
        note=body.note,
    )
    return {"id": oid}


@app.delete("/availability/overrides/{override_id}")
def delete_availability_override(override_id: int) -> dict[str, Any]:
    conn = _conn()
    dbstore.delete_availability_override(conn, override_id)
    return {"ok": True}


def _collect_work(conn, project_id: int | None) -> list[forecast_mod.WorkItem]:
    """Turn pending vulnerabilities + queued sessions into forecastable work.

    - needs_delve vulnerabilities with positive effort_hours become items
      priced in agile hours, prioritized by impact*likelihood.
    - queued sessions with a budget_hours become items too, priced at their
      remaining_hours (so a halted-then-queued session picks up where it
      left off). These sit above freshly-ranked findings via a priority
      boost so the user's explicit queue choices beat auto-scheduling.
    """
    work: list[forecast_mod.WorkItem] = []
    params: list[Any] = []
    proj_sql = ""
    if project_id is not None:
        proj_sql = "AND v.project_id = ?"
        params.append(project_id)
    rows = conn.execute(
        f"""
        SELECT v.id, v.project_id, v.title, v.priority, v.effort_hours,
               p.name AS project_name
        FROM vulnerability v JOIN project p ON p.id = v.project_id
        WHERE v.status = 'needs_delve' AND v.effort_hours IS NOT NULL
              AND v.effort_hours > 0 {proj_sql}
        ORDER BY v.priority DESC, v.id ASC
        """,
        params,
    ).fetchall()
    for r in rows:
        work.append(
            forecast_mod.WorkItem(
                kind="vulnerability",
                id=int(r["id"]),
                project_id=int(r["project_id"]),
                project_name=r["project_name"],
                title=r["title"],
                hours_remaining=float(r["effort_hours"]),
                priority=int(r["priority"] or 0),
            )
        )

    sess_params: list[Any] = []
    sess_proj_sql = ""
    if project_id is not None:
        sess_proj_sql = "AND s.project_id = ?"
        sess_params.append(project_id)
    sessions = conn.execute(
        f"""
        SELECT s.id, s.project_id, s.type, s.risk_lens, s.remaining_hours,
               s.budget_hours, p.name AS project_name
        FROM session s JOIN project p ON p.id = s.project_id
        WHERE s.status IN ('queued','halted')
              AND COALESCE(s.remaining_hours, s.budget_hours, 0) > 0
              {sess_proj_sql}
        ORDER BY s.scheduled_for ASC
        """,
        sess_params,
    ).fetchall()
    for r in sessions:
        remaining = float(r["remaining_hours"] or r["budget_hours"] or 0)
        if remaining <= 0:
            continue
        work.append(
            forecast_mod.WorkItem(
                kind="session",
                id=int(r["id"]),
                project_id=int(r["project_id"]),
                project_name=r["project_name"],
                title=f"{r['type']} · {r['risk_lens']}",
                hours_remaining=remaining,
                # Queued sessions outrank raw findings so the user's explicit
                # picks always schedule first. +1000 is a safe stomp since
                # vuln priorities cap at 25 (5x5).
                priority=1000,
            )
        )
    return work


def _load_availability(conn) -> tuple[list[tuple[int, int]], list[forecast_mod.OverrideRange]]:
    cells = dbstore.list_availability_cells(conn)
    raw_overrides = dbstore.list_availability_overrides(conn)
    ov_ranges: list[forecast_mod.OverrideRange] = []
    for row in raw_overrides:
        try:
            start = datetime.fromisoformat(str(row["start_at"]).replace(" ", "T"))
            end = datetime.fromisoformat(str(row["end_at"]).replace(" ", "T"))
        except ValueError:
            continue
        ov_ranges.append(
            forecast_mod.OverrideRange(start_at=start, end_at=end, mode=row["mode"])
        )
    return cells, ov_ranges


@app.get("/queue/forecast")
def queue_forecast(project_id: int | None = None, days: int = 7) -> dict[str, Any]:
    """Return the queue forecast: windows + items placed in each, plus ETAs.

    - `project_id` filters work to one project (still uses global availability).
    - `days` is the horizon, capped to 30 to keep the response small.
    """
    conn = _conn()
    cells, overrides = _load_availability(conn)
    work = _collect_work(conn, project_id)
    plan = forecast_mod.build_forecast(
        now=datetime.now(),
        horizon_days=max(1, min(int(days), 30)),
        cells=cells,
        overrides=overrides,
        work=work,
    )

    def _dt(d: datetime) -> str:
        return d.isoformat(sep=" ", timespec="minutes")

    windows_out: list[dict[str, Any]] = []
    for w in plan.windows:
        windows_out.append(
            {
                "start_at": _dt(w.start_at),
                "end_at": _dt(w.end_at),
                "capacity_hours": round(w.capacity_hours, 2),
                "used_hours": round(w.used_hours, 2),
                "free_hours": round(w.free_hours, 2),
                "assignments": [
                    {
                        "item_kind": a.item_kind,
                        "item_id": a.item_id,
                        "project_id": a.project_id,
                        "project_name": a.project_name,
                        "title": a.title,
                        "start_at": _dt(a.start_at),
                        "end_at": _dt(a.end_at),
                        "hours": a.hours,
                        "continued_from_prior_window": a.continued_from_prior_window,
                        "continues_into_next_window": a.continues_into_next_window,
                    }
                    for a in w.assignments
                ],
            }
        )

    return {
        "windows": windows_out,
        "unscheduled": [
            {
                "item_kind": u.kind,
                "item_id": u.id,
                "project_id": u.project_id,
                "project_name": u.project_name,
                "title": u.title,
                "hours_remaining": u.hours_remaining,
                "priority": u.priority,
            }
            for u in plan.unscheduled
        ],
    }


# ---------- mutations ----------

@app.post("/sessions/queue")
def post_queue_session(body: QueueSessionBody) -> dict[str, Any]:
    cfg = _load_cfg()
    sid = queue_session(
        cfg["paths"]["db"],
        project_id=body.project_id,
        type_=body.type,
        risk_lens=body.risk_lens,
        interest_prompt=body.interest_prompt,
        scheduled_for=body.scheduled_for,
        recurrence_cron=body.recurrence_cron,
        session_pct_cap=body.session_pct_cap,
        budget_hours=body.budget_hours,
    )
    return {"session_id": sid}


@app.post("/sessions/{session_id}/cancel")
def cancel_session(session_id: int) -> dict[str, Any]:
    conn = _conn()
    conn.execute(
        "UPDATE session SET status='cancelled' WHERE id=? AND status='queued'",
        (session_id,),
    )
    return {"ok": True}


@app.post("/vulnerabilities/{vuln_id}/status")
def override_status(vuln_id: int, body: StatusOverrideBody) -> dict[str, Any]:
    conn = _conn()
    conn.execute(
        "UPDATE vulnerability SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (body.status, vuln_id),
    )
    dbstore.append_journal(
        conn,
        vulnerability_id=vuln_id,
        run_id=None,
        agent="user",
        action="status_changed",
        payload={"to": body.status, "note": body.note},
    )
    return {"ok": True}


@app.post("/tokens/{token_id}/validate")
def validate_token(token_id: int) -> dict[str, Any]:
    conn = _conn()
    token = conn.execute(
        "SELECT * FROM github_token WHERE id=?", (token_id,)
    ).fetchone()
    if not token:
        raise HTTPException(404, "token not found")
    # Global validation: probe every repo across every project this token is
    # linked to (union). Unlinked tokens still get a timestamped identity
    # check so the UI can show "last checked" even before binding.
    repo_rows = conn.execute(
        """
        SELECT DISTINCT r.owner, r.name
        FROM repo r
        JOIN project p ON p.id = r.project_id
        WHERE p.read_token_id = ? OR p.issues_token_id = ?
        ORDER BY r.owner, r.name
        """,
        (token_id, token_id),
    ).fetchall()
    repos = [(r["owner"], r["name"]) for r in repo_rows]
    intended_for_issues = token["scope"] in ("read_and_issues", "issues_only")
    try:
        result = token_validator.validate_token_global(
            token_label=token["label"],
            secret_ref=token["secret_ref"],
            scope=token["scope"],
            repos=repos,
            intended_for_issues=intended_for_issues,
        )
    except RuntimeError as exc:
        # Missing env var is a configuration problem, not a 400 for the UI.
        # Stamp the failure so the timestamp still advances.
        token_validator.store_identity_failure(conn, token_id, str(exc))
        raise HTTPException(400, str(exc))
    token_validator.store_validation_result(conn, token_id, result)
    return result.as_dict()


@app.post("/drafts/promote")
def promote_drafts(body: PromoteBody) -> dict[str, Any]:
    conn = _conn()
    try:
        outcomes = promote_mod.promote_batch(
            conn,
            project_id=body.project_id,
            draft_issue_ids=body.draft_issue_ids,
            approved_by=body.approved_by,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return {"outcomes": [o.__dict__ for o in outcomes]}
