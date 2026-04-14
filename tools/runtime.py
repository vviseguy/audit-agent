"""Per-run context that tools can reach without it being passed as an argument.

The orchestrator sets a RunContextHandle at the start of a session; tools
like `record_journal` or `create_draft_issue` use it to talk to the DB
without needing the engine to thread a DB handle through every call.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from typing import Any

from db import store as dbstore


class RuntimeError_(RuntimeError):
    pass


@dataclass
class RunContextHandle:
    conn: sqlite3.Connection
    run_id: int
    project_id: int
    session_id: int
    current_agent: str = "system"

    def append_journal(
        self,
        *,
        vulnerability_id: int | None,
        agent: str,
        action: str,
        payload: dict[str, Any] | None,
    ) -> int:
        return dbstore.append_journal(
            self.conn,
            vulnerability_id=vulnerability_id,
            run_id=self.run_id,
            agent=agent,
            action=action,
            payload=payload,
        )


_local = threading.local()


def set_run_context(ctx: RunContextHandle) -> None:
    _local.ctx = ctx


def get_run_context() -> RunContextHandle:
    ctx = getattr(_local, "ctx", None)
    if ctx is None:
        raise RuntimeError_(
            "no run context set; orchestrator must call runtime.set_run_context() first"
        )
    return ctx


def set_current_agent(name: str) -> None:
    ctx = get_run_context()
    ctx.current_agent = name
