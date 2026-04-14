"""Offline stand-in for SDKEngine used by smoke scripts.

The real engine drives Claude Code via claude-agent-sdk. For offline smoke
tests we don't want to spin up the CLI, so this ScriptedEngine takes a
callable that produces the tool calls the model "would" emit, invokes
them against the tool registry (so side effects actually persist to the
test DB), and returns an AgentResult shaped the same way SDKEngine does.
"""

from __future__ import annotations

from typing import Any, Callable

from engine import registry
from engine.loader import AgentSpec
from engine.runner import AgentResult, RunContext


ScriptFn = Callable[[AgentSpec, str], list[dict[str, Any]]]


class ScriptedEngine:
    def __init__(self, script: ScriptFn, *, final_text: str = "done") -> None:
        self._script = script
        self._final_text = final_text

    def run(
        self,
        agent: AgentSpec,
        ctx: RunContext,
        user_message: str,
        max_loops: int = 8,
    ) -> AgentResult:
        ctx.guard.check(agent.name)

        calls = self._script(agent, user_message)
        tool_uses: list[dict[str, Any]] = []
        for i, call in enumerate(calls):
            name = call["name"]
            args = call.get("input") or {}
            spec = registry.get(name)
            spec.func(**args)
            tool_uses.append(
                {
                    "id": call.get("id") or f"tu_{i}",
                    "name": name,
                    "input": args,
                }
            )

        tokens_in = 200
        tokens_out = 60
        ctx.guard.record(agent.name, tokens_in, tokens_out)

        return AgentResult(
            text=self._final_text,
            tool_uses=tool_uses,
            stop_reason="end_turn",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
