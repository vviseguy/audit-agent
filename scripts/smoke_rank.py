"""Offline smoke test for the Ranker pass.

Uses ScriptedEngine instead of a real SDKEngine: the scripted response
emits a single `rank_candidates_batch` tool call, which the engine stub
dispatches into the real tool registry so vulnerability rows and
journal entries land in a temp SQLite DB.

Run with:
    python scripts/smoke_rank.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-stub")
os.environ.setdefault("CHROMA_PATH", tempfile.mkdtemp(prefix="chroma_smoke_"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import store as dbstore  # noqa: E402
from engine.budget import BudgetGuard  # noqa: E402
from engine.loader import load_agent  # noqa: E402
from engine.runner import RunContext  # noqa: E402
from orchestrator import rank_pass  # noqa: E402
from scanner.semgrep_runner import Candidate  # noqa: E402
from scripts._mock_engine import ScriptedEngine  # noqa: E402
from tools import all as _register_tools  # noqa: E402, F401
from tools import runtime  # noqa: E402


def _rank_script(agent, user_msg: str) -> list[dict]:
    m = re.search(r"(\[.*\])", user_msg, flags=re.DOTALL)
    cands = json.loads(m.group(1)) if m else []
    rankings = []
    for c in cands:
        rankings.append(
            {
                "candidate_id": c["candidate_id"],
                "cwe_id": c.get("cwe_id") or "CWE-20",
                "path": c["path"],
                "line_start": c["line_start"],
                "line_end": c["line_end"],
                "title": f"Stub ranking for {c['rule_id']}",
                "impact": 3,
                "likelihood": 3,
                "status": "needs_delve",
                "effort_hours": 2.0,
                "rationale": "Stubbed test ranking: priority 9, routed for delve.",
            }
        )
    return [
        {
            "name": "rank_candidates_batch",
            "input": {"rankings": rankings},
        }
    ]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_rank_"))
    db_path = tmp / "audit.db"
    clone = tmp / "clone"
    clone.mkdir()
    (clone / "app.py").write_text(
        "import sqlite3\n"
        "def handler(req):\n"
        "    q = req.args.get('q')\n"
        "    db = sqlite3.connect('a.db')\n"
        "    db.execute(f\"SELECT * FROM users WHERE name = '{q}'\")\n",
        encoding="utf-8",
    )

    dbstore.init(db_path)
    conn = dbstore.connect(db_path)
    dbstore.upsert_cwe(
        conn,
        [
            {
                "id": "CWE-20",
                "name": "Improper Input Validation",
                "short_desc": "",
                "detail": "",
                "consequences": "",
                "mitigations": "",
                "parent_id": None,
            },
            {
                "id": "CWE-89",
                "name": "SQL Injection",
                "short_desc": "",
                "detail": "",
                "consequences": "",
                "mitigations": "",
                "parent_id": None,
            },
        ],
    )
    conn.execute(
        "INSERT INTO project(name, default_risk_lens) VALUES('smoke','balanced')"
    )
    proj_id = conn.execute("SELECT id FROM project WHERE name='smoke'").fetchone()["id"]
    conn.execute(
        "INSERT INTO repo(project_id, url, owner, name, clone_path) "
        "VALUES(?, ?, ?, ?, ?)",
        (proj_id, "https://example.invalid/smoke/repo", "smoke", "repo", str(clone)),
    )
    repo_id = conn.execute("SELECT id FROM repo WHERE project_id=?", (proj_id,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO session(project_id, type, risk_lens, scheduled_for) "
        "VALUES(?, 'rank', 'balanced', CURRENT_TIMESTAMP)",
        (proj_id,),
    )
    session_id = conn.execute("SELECT id FROM session WHERE project_id=?", (proj_id,)).fetchone()["id"]
    run_id = dbstore.create_run(conn, session_id)

    rctx = runtime.RunContextHandle(
        conn=conn, run_id=run_id, project_id=proj_id, session_id=session_id
    )
    guard = BudgetGuard(
        daily_token_budget=2_000_000,
        session_pct_cap=30.0,
        tokens_per_minute_cap=40_000,
        session_deadline_epoch=time.time() + 3600,
        agent_call_caps={},
    )
    agent = load_agent(ROOT / "agents" / "ranker.yaml")
    engine = ScriptedEngine(_rank_script)
    eng_ctx = RunContext(
        run_id=run_id,
        project_id=proj_id,
        session_id=session_id,
        guard=guard,
        extra_system_blocks=[],
    )

    candidates = [
        Candidate(
            candidate_id="python.lang.security.audit.sql-injection:app.py:5",
            rule_id="python.lang.security.audit.sql-injection",
            cwe_id="CWE-89",
            path="app.py",
            line_start=5,
            line_end=5,
            severity="high",
            message="Possible SQL injection via f-string.",
            snippet="db.execute(f\"SELECT * FROM users WHERE name = '{q}'\")",
        ),
        Candidate(
            candidate_id="python.lang.security.audit.tainted-input:app.py:3",
            rule_id="python.lang.security.audit.tainted-input",
            cwe_id=None,
            path="app.py",
            line_start=3,
            line_end=3,
            severity="medium",
            message="Unvalidated user input.",
            snippet="q = req.args.get('q')",
        ),
    ]

    result = rank_pass.run(
        agent=agent,
        engine=engine,
        eng_ctx=eng_ctx,
        rctx=rctx,
        repo_id=repo_id,
        repo_clone_path=clone,
        candidates=candidates,
    )
    print("pass result:", result)

    vulns = [
        dict(r)
        for r in conn.execute(
            "SELECT path, line_start, cwe_id, impact, likelihood, priority, status, title "
            "FROM vulnerability ORDER BY id"
        ).fetchall()
    ]
    journals = [
        dict(r)
        for r in conn.execute(
            "SELECT agent, action FROM journal_entry ORDER BY id"
        ).fetchall()
    ]
    print("vulnerabilities:", vulns)
    print("journals:", journals)

    assert len(vulns) == 2, f"expected 2 vuln rows, got {len(vulns)}"
    assert all(v["priority"] == 9 for v in vulns)
    assert all(v["status"] == "needs_delve" for v in vulns)
    assert any(j["action"] == "ranked" for j in journals)

    effort_row = conn.execute(
        "SELECT effort_hours FROM vulnerability ORDER BY id"
    ).fetchall()
    assert all(r["effort_hours"] == 2.0 for r in effort_row), effort_row
    print("RANK PASS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
