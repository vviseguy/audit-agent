"""Offline smoke test for the Ranker pass.

Stubs the Anthropic client so the agent 'responds' with a single
`rank_candidates_batch` tool_use, and bypasses Semgrep by handing in
pre-built Candidate objects. Confirms that vulnerability rows and
journal entries get written to a temp SQLite DB.

Run with:
    python scripts/smoke_rank.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-stub")
os.environ.setdefault("CHROMA_PATH", tempfile.mkdtemp(prefix="chroma_smoke_"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import store as dbstore  # noqa: E402
from engine.budget import BudgetGuard  # noqa: E402
from engine.loader import load_agent  # noqa: E402
from engine.runner import Engine, RunContext  # noqa: E402
from orchestrator import rank_pass  # noqa: E402
from scanner.semgrep_runner import Candidate  # noqa: E402
from tools import all as _register_tools  # noqa: E402, F401
from tools import runtime  # noqa: E402


@dataclass
class _StubUsage:
    input_tokens: int = 120
    output_tokens: int = 45


@dataclass
class _StubBlock:
    type: str
    id: str = ""
    name: str = ""
    input: dict | None = None
    text: str = ""


@dataclass
class _StubResponse:
    content: list
    usage: _StubUsage
    stop_reason: str = "tool_use"


class _StubMessages:
    def __init__(self, parent: "_StubClient") -> None:
        self.parent = parent

    def create(self, **kwargs):
        return self.parent._next_response(kwargs)


class _StubClient:
    """Fakes the Anthropic client. First call: emits rank_candidates_batch
    tool_use with rankings for every candidate in the batch. Second call
    (after tool_result): emits end_turn with a short text."""

    def __init__(self) -> None:
        self.messages = _StubMessages(self)
        self._calls = 0

    def _next_response(self, kwargs: dict) -> _StubResponse:
        self._calls += 1
        messages = kwargs["messages"]
        last_user = messages[0]["content"] if self._calls == 1 else ""
        if self._calls == 1:
            # Parse the candidate list from the user_msg JSON tail.
            import json as _json
            import re

            m = re.search(r"(\[.*\])", last_user, flags=re.DOTALL)
            cands = _json.loads(m.group(1)) if m else []
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
            return _StubResponse(
                content=[
                    _StubBlock(
                        type="tool_use",
                        id="tu_1",
                        name="rank_candidates_batch",
                        input={"rankings": rankings},
                    )
                ],
                usage=_StubUsage(),
                stop_reason="tool_use",
            )
        return _StubResponse(
            content=[_StubBlock(type="text", text="done")],
            usage=_StubUsage(input_tokens=30, output_tokens=5),
            stop_reason="end_turn",
        )


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
    engine = Engine(prompts_base=ROOT / "prompts", client=_StubClient())
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
