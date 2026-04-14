"""Offline smoke test for the project importer + scheduler.

Imports a temporary project YAML into a temp DB, queues a session with
scheduled_for=now, runs one scheduler tick with a stub dispatcher, and
asserts that the session was moved to 'done' and a run row exists.

Run with:
    python scripts/smoke_scheduler.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-stub")
os.environ.setdefault("CHROMA_PATH", tempfile.mkdtemp(prefix="chroma_sched_"))

from db import store as dbstore  # noqa: E402
from server.dispatch import DispatchResult  # noqa: E402
from server.scheduler import SessionScheduler, queue_session  # noqa: E402
from scripts.import_project import import_project  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_sched_"))
    db_path = tmp / "audit.db"
    log_dir = tmp / "logs"

    yaml_path = tmp / "proj.yaml"
    yaml_path.write_text(
        """
name: smoke
default_risk_lens: balanced
daily_token_budget: 1000000
per_session_pct_cap: 20
create_issues: false
github_tokens:
  - label: "smoke read"
    secret_ref: GITHUB_PAT_READ
    scope: read_only
    use_for: read
repos:
  - url: https://example.invalid/smoke/repo
    owner: smoke
    name: repo
    branch: main
""".strip(),
        encoding="utf-8",
    )

    imported = import_project(yaml_path, str(db_path))
    print("imported:", imported)
    assert imported["project_id"]
    assert len(imported["repo_ids"]) == 1

    session_id = queue_session(
        str(db_path),
        project_id=imported["project_id"],
        type_="understand",
        risk_lens="balanced",
        interest_prompt=None,
        scheduled_for=datetime.now(),
        recurrence_cron=None,
        session_pct_cap=20.0,
    )
    print("queued session:", session_id)

    dispatched: list[int] = []

    def _stub_dispatch(run_id, *, cfg, log_dir):
        dispatched.append(run_id)
        return DispatchResult(
            run_id=run_id, exit_code=0, log_path=str(log_dir / f"run-{run_id}.log"),
            mode="in_process",
        )

    cfg = {
        "paths": {"db": str(db_path), "clones": str(tmp / "clones"), "chroma": str(tmp / "chroma")},
        "concurrency": {"max_active_sessions": 2},
    }
    sched = SessionScheduler(cfg, log_dir=log_dir, dispatcher=_stub_dispatch)
    # Don't actually start APScheduler — just drive _tick directly.
    sched._tick()

    # Wait for the launched thread to finish. It's synchronous in stub mode.
    import time

    for _ in range(20):
        if dispatched:
            break
        time.sleep(0.05)
    for _ in range(40):
        conn = dbstore.connect(str(db_path))
        row = conn.execute(
            "SELECT status FROM session WHERE id=?", (session_id,)
        ).fetchone()
        conn.close()
        if row["status"] != "queued":
            break
        time.sleep(0.05)

    conn = dbstore.connect(str(db_path))
    session_status = conn.execute(
        "SELECT status FROM session WHERE id=?", (session_id,)
    ).fetchone()["status"]
    run_rows = [
        dict(r)
        for r in conn.execute(
            "SELECT id, session_id, status FROM run WHERE session_id=?", (session_id,)
        ).fetchall()
    ]
    conn.close()

    print("session status:", session_status)
    print("runs:", run_rows)
    print("dispatched:", dispatched)

    assert dispatched, "stub dispatcher was not called"
    assert session_status == "done", f"expected 'done', got {session_status!r}"
    assert len(run_rows) == 1
    print("SCHEDULER OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
