"""Offline smoke test for the Delver pass.

Uses ScriptedEngine: the scripted response invokes
`retrieve_similar_vulnerabilities` then `create_draft_issue` through
the real tool registry, so draft_issue + journal + vulnerability
status transitions land in a temp SQLite DB.

Run with:
    python scripts/smoke_delve.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-stub")
os.environ.setdefault("CHROMA_PATH", tempfile.mkdtemp(prefix="chroma_delve_"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import store as dbstore  # noqa: E402
from engine.budget import BudgetGuard  # noqa: E402
from engine.loader import load_agent  # noqa: E402
from engine.runner import RunContext  # noqa: E402
from orchestrator import delve_pass  # noqa: E402
from scripts._mock_engine import ScriptedEngine  # noqa: E402
from tools import all as _register_tools  # noqa: E402, F401
from tools import runtime  # noqa: E402


def _delve_script(agent, user_msg: str) -> list[dict]:
    m = re.search(r'"vulnerability_id":\s*(\d+)', user_msg)
    vuln_id = int(m.group(1)) if m else 1
    return [
        {
            "name": "retrieve_similar_vulnerabilities",
            "input": {"query": "SQL injection in user search", "k": 3},
        },
        {
            "name": "create_draft_issue",
            "input": {
                "vulnerability_id": vuln_id,
                "title": "SQL injection in /u/<name> handler",
                "severity": "high",
                "exploit_scenario": (
                    "An attacker submits `?q=' OR 1=1 --` to the handler at "
                    "app.py:5. The f-string interpolates the value directly "
                    "into the SELECT, returning every row in the users table."
                ),
                "remediation": (
                    "Use a parameterized query: "
                    "`db.execute('SELECT * FROM users WHERE name = ?', (q,))`. "
                    "Do not build SQL with f-strings or concatenation."
                ),
                "code_excerpt": (
                    "q = req.args.get('q')\n"
                    "db.execute(f\"SELECT * FROM users WHERE name = '{q}'\")"
                ),
                "confidence": 0.85,
                "references": ["CWE-89"],
            },
        },
    ]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_delve_"))
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
    (clone / "CLAUDE.md").write_text(
        "# app\nHTTP entry points. Trust boundary: true.\n", encoding="utf-8"
    )

    dbstore.init(db_path)
    conn = dbstore.connect(db_path)
    dbstore.upsert_cwe(
        conn,
        [
            {
                "id": "CWE-89",
                "name": "SQL Injection",
                "short_desc": "Improper neutralization of SQL.",
                "detail": "",
                "consequences": "",
                "mitigations": "Parameterize queries.",
                "parent_id": None,
            }
        ],
    )
    conn.execute(
        "INSERT INTO project(name, default_risk_lens) VALUES('smoke','balanced')"
    )
    proj_id = conn.execute("SELECT id FROM project WHERE name='smoke'").fetchone()["id"]
    conn.execute(
        "INSERT INTO repo(project_id, url, owner, name, clone_path) VALUES(?, ?, ?, ?, ?)",
        (proj_id, "https://example.invalid/smoke/repo", "smoke", "repo", str(clone)),
    )
    repo_id = conn.execute("SELECT id FROM repo WHERE project_id=?", (proj_id,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO session(project_id, type, risk_lens, interest_prompt, scheduled_for) "
        "VALUES(?, 'delve', 'high_impact', NULL, CURRENT_TIMESTAMP)",
        (proj_id,),
    )
    session_id = conn.execute("SELECT id FROM session WHERE project_id=?", (proj_id,)).fetchone()["id"]
    run_id = dbstore.create_run(conn, session_id)

    conn.execute(
        """
        INSERT INTO vulnerability(
            project_id, repo_id, path, line_start, line_end, cwe_id,
            title, short_desc, impact, likelihood, priority, status,
            first_seen_run_id, last_seen_run_id
        ) VALUES(?, ?, 'app.py', 5, 5, 'CWE-89',
                 'SQL injection via f-string in handler',
                 'unparameterized SELECT concatenation', 4, 4, 16, 'needs_delve',
                 ?, ?)
        """,
        (proj_id, repo_id, run_id, run_id),
    )

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
    agent = load_agent(ROOT / "agents" / "delver.yaml")
    engine = ScriptedEngine(_delve_script)
    eng_ctx = RunContext(
        run_id=run_id,
        project_id=proj_id,
        session_id=session_id,
        guard=guard,
        extra_system_blocks=[],
    )

    result = delve_pass.run(
        agent=agent,
        engine=engine,
        eng_ctx=eng_ctx,
        rctx=rctx,
        repo_id=repo_id,
        repo_clone_path=clone,
        risk_lens="high_impact",
        interest_prompt=None,
        top_k=5,
    )
    print("pass result:", result)

    drafts = [
        dict(r)
        for r in conn.execute(
            "SELECT id, vulnerability_id, title, severity, status FROM draft_issue"
        ).fetchall()
    ]
    vulns = [
        dict(r)
        for r in conn.execute(
            "SELECT id, status FROM vulnerability"
        ).fetchall()
    ]
    journals = [
        dict(r)
        for r in conn.execute(
            "SELECT agent, action FROM journal_entry ORDER BY id"
        ).fetchall()
    ]
    print("drafts:", drafts)
    print("vulns:", vulns)
    print("journals:", journals)

    assert len(drafts) == 1, f"expected 1 draft, got {len(drafts)}"
    assert drafts[0]["severity"] == "high"
    assert drafts[0]["status"] == "draft"
    assert vulns[0]["status"] == "delved"
    assert any(j["action"] == "issue_drafted" for j in journals)
    assert any(j["action"] == "delved" for j in journals)
    print("DELVE PASS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
