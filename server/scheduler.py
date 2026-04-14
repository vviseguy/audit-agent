"""APScheduler-backed session runner for the host process.

Responsibilities:
    - Periodically scan `session WHERE status='queued' AND scheduled_for <= now`.
    - Fire each due session by creating a `run` row and handing it to
      `server.dispatch.dispatch_run`. The dispatch wrapper decides whether
      to spawn a Docker container or run in-process.
    - Respect the global concurrency cap (`config.concurrency.max_active_sessions`).
    - On boot, optionally surface missed sessions as "catch-up" candidates.

Pure policy — this module owns *when* to run, not *how* to run an agent.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from db import store as dbstore
from server.dispatch import DispatchResult, dispatch_run

log = logging.getLogger(__name__)


class SessionScheduler:
    def __init__(
        self,
        cfg: dict,
        *,
        log_dir: Path,
        tick_seconds: int = 10,
        dispatcher: Callable[..., DispatchResult] | None = None,
    ) -> None:
        self.cfg = cfg
        self.db_path = cfg["paths"]["db"]
        self.log_dir = Path(log_dir)
        self.tick_seconds = tick_seconds
        self.max_active = int(cfg.get("concurrency", {}).get("max_active_sessions", 2))
        self.dispatcher = dispatcher or dispatch_run
        self._active: dict[int, threading.Thread] = {}
        self._lock = threading.Lock()
        self._scheduler = BackgroundScheduler()

    # ---------- lifecycle ----------

    def start(self) -> None:
        self._scheduler.add_job(
            self._tick,
            trigger=IntervalTrigger(seconds=self.tick_seconds),
            id="session_tick",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        log.info("scheduler started (tick=%ds)", self.tick_seconds)

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
        log.info("scheduler shut down")

    # ---------- tick ----------

    def _tick(self) -> None:
        with self._lock:
            active_count = sum(1 for t in self._active.values() if t.is_alive())
            if active_count >= self.max_active:
                return
            slots = self.max_active - active_count

        conn = dbstore.connect(self.db_path)
        # Gate on the user's availability grid. An empty grid means "no
        # restriction" so dev flows keep working out of the box; once the
        # user sets availability cells in the Queue page, the scheduler
        # only fires during those hours.
        if not self._is_now_available(conn):
            conn.close()
            return
        due = conn.execute(
            """
            SELECT id FROM session
            WHERE status='queued' AND scheduled_for <= CURRENT_TIMESTAMP
            ORDER BY scheduled_for ASC
            LIMIT ?
            """,
            (slots,),
        ).fetchall()
        conn.close()

        for row in due:
            self._launch_session(int(row["id"]))

    def _is_now_available(self, conn) -> bool:
        cells = dbstore.list_availability_cells(conn)
        if not cells:
            return True  # unconfigured → unrestricted, preserves existing behavior
        now = datetime.now()
        dow = now.weekday()
        hour = now.hour
        in_cell = (dow, hour) in set(cells)
        hour_end = now.replace(minute=0, second=0, microsecond=0)
        forced_on = False
        forced_off = False
        for row in dbstore.list_availability_overrides(conn):
            try:
                start = datetime.fromisoformat(str(row["start_at"]).replace(" ", "T"))
                end = datetime.fromisoformat(str(row["end_at"]).replace(" ", "T"))
            except ValueError:
                continue
            if end <= hour_end or start >= now:
                continue
            if row["mode"] == "available":
                forced_on = True
            elif row["mode"] == "blocked":
                forced_off = True
        if forced_off:
            return False
        if forced_on:
            return True
        return in_cell

    def _launch_session(self, session_id: int) -> None:
        conn = dbstore.connect(self.db_path)
        conn.execute(
            "UPDATE session SET status='running' WHERE id=? AND status='queued'",
            (session_id,),
        )
        run_id = dbstore.create_run(conn, session_id)
        conn.close()

        log.info("launching session %d (run_id=%d)", session_id, run_id)

        def _runner() -> None:
            started = time.time()
            try:
                result = self.dispatcher(
                    run_id, cfg=self.cfg, log_dir=self.log_dir
                )
                log.info(
                    "session %d run %d finished: exit=%d mode=%s",
                    session_id, run_id, result.exit_code, result.mode,
                )
                # Book wall-clock hours against the session's budget. If the
                # run exited cleanly, zero out remaining so the session is
                # done. If it halted but still owes hours, drop status back
                # to 'queued' so the next open window picks it up.
                elapsed_hours = max(0.0, (time.time() - started) / 3600.0)
                conn2 = dbstore.connect(self.db_path)
                row = conn2.execute(
                    "SELECT budget_hours, remaining_hours FROM session WHERE id=?",
                    (session_id,),
                ).fetchone()
                budget = float(row["budget_hours"] or 0) if row else 0.0
                remaining = float(row["remaining_hours"] or budget) if row else 0.0
                if result.exit_code == 0:
                    new_status = "done"
                    new_remaining = 0.0
                else:
                    new_remaining = max(0.0, remaining - elapsed_hours)
                    # Leave a 15-min slack threshold: below it, call it done
                    # so a flapping session doesn't re-queue forever.
                    if new_remaining < 0.25:
                        new_status = "halted"
                        new_remaining = 0.0
                    else:
                        new_status = "queued"  # auto-resume
                conn2.execute(
                    "UPDATE session SET status=?, remaining_hours=? WHERE id=?",
                    (new_status, new_remaining, session_id),
                )
                conn2.close()
            except Exception as exc:
                log.exception("dispatch failed for run %d", run_id)
                conn2 = dbstore.connect(self.db_path)
                conn2.execute(
                    "UPDATE run SET status='error', halted_reason=? WHERE id=?",
                    (f"dispatch_exception: {exc}", run_id),
                )
                conn2.execute(
                    "UPDATE session SET status='halted' WHERE id=?",
                    (session_id,),
                )
                conn2.close()
            finally:
                with self._lock:
                    self._active.pop(session_id, None)

        t = threading.Thread(target=_runner, name=f"session-{session_id}", daemon=True)
        with self._lock:
            self._active[session_id] = t
        t.start()

    # ---------- boot-time catch-up ----------

    def surface_missed(self) -> list[int]:
        """Return sessions whose scheduled_for is in the past and still 'queued'.

        UI offers these as catch-up candidates; we don't auto-run them so the
        user isn't surprised after a machine wakes from sleep.
        """
        conn = dbstore.connect(self.db_path)
        rows = conn.execute(
            """
            SELECT id FROM session
            WHERE status='queued' AND scheduled_for < datetime('now','-1 hour')
            """
        ).fetchall()
        conn.close()
        return [int(r["id"]) for r in rows]


_DEFAULT_BUDGET_HOURS = {
    "understand": 2.0,
    "rank": 1.0,
    "delve": 4.0,
    "full": 6.0,
}


def queue_session(
    db_path: str,
    *,
    project_id: int,
    type_: str,
    risk_lens: str,
    interest_prompt: str | None,
    scheduled_for: datetime,
    recurrence_cron: str | None,
    session_pct_cap: float,
    created_by: str = "ui",
    budget_hours: float | None = None,
) -> int:
    """Insert a session row; the scheduler will pick it up on its next tick.

    `budget_hours` is the total agile-hours this session is allowed to
    consume. If omitted, we look up a type-specific default — delve
    sessions budget 4h, rank 1h, etc. remaining_hours is initialized to the
    same value so the forecast engine has something to pack.
    """
    if budget_hours is None:
        budget_hours = _DEFAULT_BUDGET_HOURS.get(type_, 2.0)
    conn = dbstore.connect(db_path)
    cur = conn.execute(
        """
        INSERT INTO session(
            project_id, type, risk_lens, interest_prompt, scheduled_for,
            recurrence_cron, session_pct_cap, budget_hours, remaining_hours,
            status, created_by
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
        """,
        (
            project_id,
            type_,
            risk_lens,
            interest_prompt,
            scheduled_for.isoformat(sep=" "),
            recurrence_cron,
            float(session_pct_cap),
            float(budget_hours),
            float(budget_hours),
            created_by,
        ),
    )
    sid = int(cur.lastrowid)
    conn.close()
    return sid
