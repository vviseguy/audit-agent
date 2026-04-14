"""Entrypoint for a single agent-side job run.

Invoked from the host scheduler as:
    python -m orchestrator.run_job <run_id>

or locally for smoke tests. Reads the run + session + project from SQLite,
sets up sandbox + runtime context, dispatches to the right pass, records
tokens + halted_reason, and exits.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import yaml

from db import store as dbstore
from engine.budget import BudgetGuard
from engine.loader import load_agent
from engine.runner import Engine, RunContext
from tools import runtime
from tools import all as _register_tools  # noqa: F401  (registers tools)

log = logging.getLogger("run_job")


def _load_config() -> dict:
    with open("config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _build_guard(
    conn, *, session_pct_cap: float, daily_token_budget: int, max_duration_min: int
) -> BudgetGuard:
    return BudgetGuard(
        daily_token_budget=daily_token_budget,
        session_pct_cap=session_pct_cap,
        tokens_per_minute_cap=40_000,
        session_deadline_epoch=time.time() + max_duration_min * 60,
        agent_call_caps={},
        tokens_used_today=dbstore.tokens_used_today(conn),
    )


def _load_run_frame(conn, run_id: int):
    run_row = conn.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
    session_row = conn.execute(
        "SELECT * FROM session WHERE id=?", (run_row["session_id"],)
    ).fetchone()
    project_row = conn.execute(
        "SELECT * FROM project WHERE id=?", (session_row["project_id"],)
    ).fetchone()
    repos = conn.execute(
        "SELECT * FROM repo WHERE project_id=?", (project_row["id"],)
    ).fetchall()
    return run_row, session_row, project_row, repos


def run_rank(
    *,
    run_id: int,
    db_path: str,
    prompts_base: Path,
    agents_base: Path,
    session_pct_cap: float,
    daily_token_budget: int,
    max_duration_min: int,
) -> dict:
    from orchestrator import rank_pass

    conn = dbstore.connect(db_path)
    _, session_row, project_row, repos = _load_run_frame(conn, run_id)

    rctx = runtime.RunContextHandle(
        conn=conn,
        run_id=run_id,
        project_id=project_row["id"],
        session_id=session_row["id"],
    )
    guard = _build_guard(
        conn,
        session_pct_cap=session_pct_cap,
        daily_token_budget=daily_token_budget,
        max_duration_min=max_duration_min,
    )

    agent = load_agent(agents_base / "ranker.yaml")
    engine = Engine(prompts_base=prompts_base)
    eng_ctx = RunContext(
        run_id=run_id,
        project_id=project_row["id"],
        session_id=session_row["id"],
        guard=guard,
        extra_system_blocks=[],
    )

    summary = {"repos": []}
    halted: str | None = None
    for repo in repos:
        clone_path = repo["clone_path"]
        if not clone_path or not Path(clone_path).is_dir():
            log.warning("repo %s has no clone_path; skipping", repo["url"])
            continue
        result = rank_pass.run(
            agent=agent,
            engine=engine,
            eng_ctx=eng_ctx,
            rctx=rctx,
            repo_id=repo["id"],
            repo_clone_path=Path(clone_path),
        )
        summary["repos"].append({"repo_id": repo["id"], **result})
        if result.get("halted"):
            halted = result["halted"]
            break

    dbstore.finish_run(
        conn,
        run_id,
        status="halted" if halted else "done",
        tokens_in=guard.session_tokens_in,
        tokens_out=guard.session_tokens_out,
        cost_usd=0.0,
        pct_daily=guard.pct_daily_used,
        halted_reason=halted,
    )
    dbstore.add_tokens_today(
        conn, guard.session_tokens_in, guard.session_tokens_out, 0.0
    )
    dbstore.append_journal(
        conn,
        vulnerability_id=None,
        run_id=run_id,
        agent="ranker",
        action="pass_done",
        payload=summary,
    )
    return summary


def run_delve(
    *,
    run_id: int,
    db_path: str,
    prompts_base: Path,
    agents_base: Path,
    session_pct_cap: float,
    daily_token_budget: int,
    max_duration_min: int,
) -> dict:
    from orchestrator import delve_pass

    conn = dbstore.connect(db_path)
    _, session_row, project_row, repos = _load_run_frame(conn, run_id)

    rctx = runtime.RunContextHandle(
        conn=conn,
        run_id=run_id,
        project_id=project_row["id"],
        session_id=session_row["id"],
    )
    guard = _build_guard(
        conn,
        session_pct_cap=session_pct_cap,
        daily_token_budget=daily_token_budget,
        max_duration_min=max_duration_min,
    )

    agent = load_agent(agents_base / "delver.yaml")
    engine = Engine(prompts_base=prompts_base)
    eng_ctx = RunContext(
        run_id=run_id,
        project_id=project_row["id"],
        session_id=session_row["id"],
        guard=guard,
        extra_system_blocks=[],
    )

    summary = {"repos": []}
    halted: str | None = None
    for repo in repos:
        clone_path = repo["clone_path"]
        if not clone_path or not Path(clone_path).is_dir():
            log.warning("repo %s has no clone_path; skipping", repo["url"])
            continue
        result = delve_pass.run(
            agent=agent,
            engine=engine,
            eng_ctx=eng_ctx,
            rctx=rctx,
            repo_id=repo["id"],
            repo_clone_path=Path(clone_path),
            risk_lens=session_row["risk_lens"],
            interest_prompt=session_row["interest_prompt"],
            top_k=5,
        )
        summary["repos"].append({"repo_id": repo["id"], **result})
        if result.get("halted"):
            halted = result["halted"]
            break

    dbstore.finish_run(
        conn,
        run_id,
        status="halted" if halted else "done",
        tokens_in=guard.session_tokens_in,
        tokens_out=guard.session_tokens_out,
        cost_usd=0.0,
        pct_daily=guard.pct_daily_used,
        halted_reason=halted,
    )
    dbstore.add_tokens_today(
        conn, guard.session_tokens_in, guard.session_tokens_out, 0.0
    )
    dbstore.append_journal(
        conn,
        vulnerability_id=None,
        run_id=run_id,
        agent="delver",
        action="pass_done",
        payload=summary,
    )
    return summary


def run_understand(
    *,
    run_id: int,
    db_path: str,
    prompts_base: Path,
    agents_base: Path,
    session_pct_cap: float,
    daily_token_budget: int,
    max_duration_min: int,
) -> dict:
    from orchestrator import understand_pass

    conn = dbstore.connect(db_path)
    run_row = conn.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
    session_row = conn.execute(
        "SELECT * FROM session WHERE id=?", (run_row["session_id"],)
    ).fetchone()
    project_row = conn.execute(
        "SELECT * FROM project WHERE id=?", (session_row["project_id"],)
    ).fetchone()
    repos = conn.execute(
        "SELECT * FROM repo WHERE project_id=?", (project_row["id"],)
    ).fetchall()

    rctx = runtime.RunContextHandle(
        conn=conn,
        run_id=run_id,
        project_id=project_row["id"],
        session_id=session_row["id"],
    )
    guard = BudgetGuard(
        daily_token_budget=daily_token_budget,
        session_pct_cap=session_pct_cap,
        tokens_per_minute_cap=40_000,
        session_deadline_epoch=time.time() + max_duration_min * 60,
        agent_call_caps={},
        tokens_used_today=dbstore.tokens_used_today(conn),
    )

    agent = load_agent(agents_base / "understander.yaml")
    engine = Engine(prompts_base=prompts_base)
    eng_ctx = RunContext(
        run_id=run_id,
        project_id=project_row["id"],
        session_id=session_row["id"],
        guard=guard,
        extra_system_blocks=[],
    )

    summary = {"repos": []}
    halted: str | None = None
    for repo in repos:
        clone_path = repo["clone_path"]
        if not clone_path or not Path(clone_path).is_dir():
            log.warning("repo %s has no clone_path; skipping", repo["url"])
            continue
        result = understand_pass.run(
            agent=agent,
            engine=engine,
            eng_ctx=eng_ctx,
            rctx=rctx,
            repo_id=repo["id"],
            repo_clone_path=Path(clone_path),
        )
        summary["repos"].append({"repo_id": repo["id"], **result})
        if result.get("halted"):
            halted = result["halted"]
            break

    dbstore.finish_run(
        conn,
        run_id,
        status="halted" if halted else "done",
        tokens_in=guard.session_tokens_in,
        tokens_out=guard.session_tokens_out,
        cost_usd=0.0,
        pct_daily=guard.pct_daily_used,
        halted_reason=halted,
    )
    dbstore.add_tokens_today(
        conn, guard.session_tokens_in, guard.session_tokens_out, 0.0
    )
    dbstore.append_journal(
        conn,
        vulnerability_id=None,
        run_id=run_id,
        agent="understander",
        action="pass_done",
        payload=summary,
    )
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id", type=int)
    args = ap.parse_args()

    cfg = _load_config()
    prompts_base = Path("prompts")
    agents_base = Path("agents")

    conn = dbstore.connect(cfg["paths"]["db"])
    session_id = conn.execute("SELECT session_id FROM run WHERE id=?", (args.run_id,)).fetchone()["session_id"]
    session_type = conn.execute("SELECT type FROM session WHERE id=?", (session_id,)).fetchone()["type"]

    common = dict(
        run_id=args.run_id,
        db_path=cfg["paths"]["db"],
        prompts_base=prompts_base,
        agents_base=agents_base,
        session_pct_cap=cfg["budgets"]["default_session_pct_cap"],
        daily_token_budget=cfg["budgets"]["daily_token_budget"],
        max_duration_min=cfg["scheduler"]["max_session_duration_minutes"],
    )

    if session_type == "understand":
        summary = run_understand(**common)
    elif session_type == "rank":
        summary = run_rank(**common)
    elif session_type == "delve":
        summary = run_delve(**common)
    else:
        log.error("session type %s not yet implemented", session_type)
        return 1

    log.info("done: %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
