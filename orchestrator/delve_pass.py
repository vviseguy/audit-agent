"""Delver pass — picks top-K `needs_delve` vulnerabilities and delves each one.

The session's risk lens is injected as a cacheable extra system block so
the base system prompt stays cacheable across calls.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from db import store as dbstore
from engine.budget import BudgetExceeded
from engine.loader import AgentSpec
from engine.runner import Engine, RunContext
from rag import project_memory
from tools import runtime, sandbox

log = logging.getLogger(__name__)


RISK_LENS_FRAGMENTS = {
    "high_impact": (
        "SESSION RISK LENS: Prioritize vulnerabilities whose successful "
        "exploitation would allow privilege escalation, data exfiltration, or "
        "remote code execution. Deprioritize findings with limited blast radius."
    ),
    "high_likelihood": (
        "SESSION RISK LENS: Prioritize vulnerabilities that are easily "
        "triggered by common user input or automated scanners. Deprioritize "
        "findings requiring unusual preconditions."
    ),
    "ui_visible": (
        "SESSION RISK LENS: Prioritize vulnerabilities in code paths reachable "
        "from public endpoints or user-facing UI. Use the Understander's "
        "trust-boundary annotations to guide selection."
    ),
    "balanced": (
        "SESSION RISK LENS: Order by impact × likelihood equally. Produce a "
        "balanced set without strong bias."
    ),
}


def _risk_lens_block(lens: str, custom: str | None) -> dict:
    if lens == "custom" and custom:
        text = f"SESSION RISK LENS (custom): {custom.strip()}"
    else:
        text = RISK_LENS_FRAGMENTS.get(lens, RISK_LENS_FRAGMENTS["balanced"])
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


def _pick_top_k(
    conn: sqlite3.Connection, *, project_id: int, k: int
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM vulnerability
        WHERE project_id=? AND status='needs_delve'
        ORDER BY priority DESC, id ASC
        LIMIT ?
        """,
        (project_id, k),
    ).fetchall()


def _build_user_msg(vuln: sqlite3.Row, claude_md_rel: str | None) -> str:
    claude_hint = (
        f"Related module note: `{claude_md_rel}` (read it if useful)."
        if claude_md_rel
        else "No Understander note exists for this directory."
    )
    payload = {
        "vulnerability_id": vuln["id"],
        "cwe_id": vuln["cwe_id"],
        "path": vuln["path"],
        "line_start": vuln["line_start"],
        "line_end": vuln["line_end"],
        "title": vuln["title"],
        "short_desc": vuln["short_desc"] or "",
        "priority": vuln["priority"],
    }
    return (
        "Delve this vulnerability:\n\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        f"{claude_hint}\n\n"
        "Read the code, check history with `retrieve_similar_vulnerabilities`, "
        "then call `create_draft_issue` or `update_draft_issue` exactly once."
    )


def _find_claude_md(repo_clone_path: Path, vuln_path: str) -> str | None:
    root = repo_clone_path.resolve()
    file = (root / vuln_path).resolve()
    try:
        file.relative_to(root)
    except ValueError:
        return None
    candidate = file.parent / "CLAUDE.md"
    if candidate.is_file():
        return candidate.relative_to(root).as_posix()
    return None


def run(
    *,
    agent: AgentSpec,
    engine: Engine,
    eng_ctx: RunContext,
    rctx: runtime.RunContextHandle,
    repo_id: int,
    repo_clone_path: Path,
    risk_lens: str,
    interest_prompt: str | None,
    top_k: int = 5,
) -> dict:
    sandbox.set_root(repo_clone_path)
    runtime.set_run_context(rctx)
    runtime.set_current_agent(agent.name)

    eng_ctx.extra_system_blocks = [_risk_lens_block(risk_lens, interest_prompt)]

    vulns = _pick_top_k(rctx.conn, project_id=rctx.project_id, k=top_k)
    log.info("delver: %d needs_delve vulnerabilities to process", len(vulns))

    delved = 0
    drafted = 0
    halted: str | None = None

    for vuln in vulns:
        if int(vuln["repo_id"]) != int(repo_id):
            continue
        claude_md = _find_claude_md(repo_clone_path, vuln["path"])
        user_msg = _build_user_msg(vuln, claude_md)
        try:
            result = engine.run(agent, eng_ctx, user_msg, max_loops=12)
        except BudgetExceeded as exc:
            halted = exc.reason
            log.warning("delver halted: %s", exc)
            break

        created = [tu for tu in result.tool_uses if tu.get("name") == "create_draft_issue"]
        updated = [tu for tu in result.tool_uses if tu.get("name") == "update_draft_issue"]
        if created or updated:
            drafted += 1
            rctx.conn.execute(
                "UPDATE vulnerability SET status='delved', updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='draft_issue'",
                (int(vuln["id"]),),
            )
        else:
            log.warning(
                "delver: vuln %s produced no draft issue", vuln["id"]
            )
        delved += 1

        project_memory.upsert_vulnerability(
            project_id=rctx.project_id,
            vulnerability_id=int(vuln["id"]),
            cwe_id=vuln["cwe_id"],
            path=vuln["path"],
            title=vuln["title"],
            short_desc=vuln["short_desc"] or "",
        )

        journal_id = dbstore.append_journal(
            rctx.conn,
            vulnerability_id=int(vuln["id"]),
            run_id=rctx.run_id,
            agent="delver",
            action="delved",
            payload={
                "tool_uses": [tu.get("name") for tu in result.tool_uses],
                "tokens": {"in": result.tokens_in, "out": result.tokens_out},
            },
        )
        project_memory.upsert_journal_entry(
            project_id=rctx.project_id,
            vulnerability_id=int(vuln["id"]),
            journal_id=journal_id,
            cwe_id=vuln["cwe_id"],
            path=vuln["path"],
            text=f"Delved: {vuln['title']}",
        )

    return {
        "vulns_seen": len(vulns),
        "delved": delved,
        "drafted": drafted,
        "halted": halted or "",
    }
