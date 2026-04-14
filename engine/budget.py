from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


class BudgetExceeded(Exception):
    """Raised when a session exceeds one of its halt conditions.

    The binding constraint is stored on the exception and persisted to
    run.halted_reason so the UI can surface it.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


HaltReason = str  # 'schedule_expired' | 'rate_limit_session_cap' |
                  # 'agent_cap' | 'daily_budget_exceeded'


@dataclass
class BudgetGuard:
    """Enforces the three concurrent limits on a session.

    1. Schedule window (wall clock).
    2. Rate limit (tokens/minute) and session cap (% of daily budget).
    3. Per-agent call cap.

    Call `check()` before every LLM invocation and `record()` after.
    """

    daily_token_budget: int
    session_pct_cap: float           # e.g., 30.0 => 30% of daily
    tokens_per_minute_cap: int
    session_deadline_epoch: float    # time.time() value; 0 disables
    agent_call_caps: dict[str, int]  # agent_name -> max calls for this run

    tokens_used_today: int = 0       # carried in from DB at session start
    session_tokens_in: int = 0
    session_tokens_out: int = 0
    agent_call_counts: dict[str, int] = field(default_factory=dict)

    _minute_window_start: float = field(default_factory=time.time)
    _minute_tokens: int = 0

    @property
    def session_total_tokens(self) -> int:
        return self.session_tokens_in + self.session_tokens_out

    @property
    def pct_daily_used(self) -> float:
        if self.daily_token_budget <= 0:
            return 0.0
        return (
            (self.tokens_used_today + self.session_total_tokens)
            / self.daily_token_budget
            * 100.0
        )

    def _session_allowance(self) -> int:
        return int(self.daily_token_budget * (self.session_pct_cap / 100.0))

    def check(self, agent_name: str) -> None:
        """Raise BudgetExceeded if any limit is breached. Call before each LLM call."""
        now = time.time()

        if self.session_deadline_epoch and now >= self.session_deadline_epoch:
            raise BudgetExceeded(
                "schedule_expired",
                f"window closed at {datetime.fromtimestamp(self.session_deadline_epoch, tz=timezone.utc).isoformat()}",
            )

        if self.session_total_tokens >= self._session_allowance():
            raise BudgetExceeded(
                "rate_limit_session_cap",
                f"session used {self.session_total_tokens} tokens, cap is {self._session_allowance()}",
            )

        if (
            self.tokens_used_today + self.session_total_tokens
            >= self.daily_token_budget
        ):
            raise BudgetExceeded(
                "daily_budget_exceeded",
                f"day total {self.tokens_used_today + self.session_total_tokens} "
                f"of {self.daily_token_budget}",
            )

        cap = self.agent_call_caps.get(agent_name)
        if cap is not None and self.agent_call_counts.get(agent_name, 0) >= cap:
            raise BudgetExceeded(
                "agent_cap",
                f"{agent_name} hit max_calls_per_job={cap}",
            )

        # Sliding-minute rate limit. Sleep (don't raise) to smooth bursts.
        if now - self._minute_window_start >= 60:
            self._minute_window_start = now
            self._minute_tokens = 0
        if self._minute_tokens >= self.tokens_per_minute_cap:
            sleep_for = 60 - (now - self._minute_window_start)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._minute_window_start = time.time()
            self._minute_tokens = 0

    def record(self, agent_name: str, tokens_in: int, tokens_out: int) -> None:
        self.session_tokens_in += tokens_in
        self.session_tokens_out += tokens_out
        self._minute_tokens += tokens_in + tokens_out
        self.agent_call_counts[agent_name] = (
            self.agent_call_counts.get(agent_name, 0) + 1
        )
