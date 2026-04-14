"""Shared engine types.

Historically this module hosted an Anthropic-SDK-backed Engine class. That
runtime was replaced by engine.sdk_runner.SDKEngine, which drives Claude
Code via claude-agent-sdk. Only the dataclasses that the orchestrator
and pass modules consume live here now.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from engine.budget import BudgetGuard


@dataclass
class RunContext:
    """Per-session state threaded into every engine call."""

    run_id: int
    project_id: int
    session_id: int
    guard: BudgetGuard
    extra_system_blocks: list[dict[str, Any]]  # cacheable blocks (cwe_context, lens)
    on_tool_call: Callable[[str, str, dict[str, Any]], None] | None = None
    on_text: Callable[[str, str], None] | None = None  # (agent, text)


@dataclass
class AgentResult:
    text: str
    tool_uses: list[dict[str, Any]]
    stop_reason: str
    tokens_in: int
    tokens_out: int
