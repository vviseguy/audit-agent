from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from anthropic import Anthropic

from engine import registry
from engine.budget import BudgetGuard
from engine.loader import AgentSpec

log = logging.getLogger(__name__)


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


class Engine:
    """Agent-independent orchestration engine.

    The engine does four things and nothing else:
      1. Build the Anthropic request from the agent spec + run context.
      2. Run the tool-use loop, resolving tool names via the registry.
      3. Check the BudgetGuard before each call; halt cleanly on breach.
      4. Record token usage.
    """

    def __init__(self, prompts_base: Path, client: Anthropic | None = None) -> None:
        self.prompts_base = Path(prompts_base)
        self.client = client or Anthropic()

    def run(
        self,
        agent: AgentSpec,
        ctx: RunContext,
        user_message: str,
        max_loops: int = 8,
    ) -> AgentResult:
        ctx.guard.check(agent.name)

        system_text = agent.load_system_prompt(self.prompts_base.parent)
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_text,
                **(
                    {"cache_control": {"type": "ephemeral"}}
                    if "system" in agent.prompt_cache
                    else {}
                ),
            }
        ]
        system_blocks.extend(ctx.extra_system_blocks)

        tools = [t.to_anthropic() for t in registry.resolve(agent.tools)]

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]

        last_text = ""
        all_tool_uses: list[dict[str, Any]] = []
        total_in = 0
        total_out = 0
        stop_reason = ""

        for _ in range(max_loops):
            ctx.guard.check(agent.name)

            response = self.client.messages.create(
                model=agent.model,
                max_tokens=agent.max_tokens,
                temperature=agent.temperature,
                system=system_blocks,
                tools=tools if tools else None,
                messages=messages,
            )

            tokens_in = getattr(response.usage, "input_tokens", 0) or 0
            tokens_out = getattr(response.usage, "output_tokens", 0) or 0
            total_in += tokens_in
            total_out += tokens_out
            ctx.guard.record(agent.name, tokens_in, tokens_out)

            stop_reason = response.stop_reason or ""
            tool_uses_this_turn: list[dict[str, Any]] = []
            text_this_turn: list[str] = []

            for block in response.content:
                if getattr(block, "type", None) == "text":
                    text_this_turn.append(block.text)
                    if ctx.on_text:
                        ctx.on_text(agent.name, block.text)
                elif getattr(block, "type", None) == "tool_use":
                    tool_uses_this_turn.append(
                        {"id": block.id, "name": block.name, "input": block.input}
                    )

            if text_this_turn:
                last_text = "\n".join(text_this_turn)
            all_tool_uses.extend(tool_uses_this_turn)

            if stop_reason != "tool_use" or not tool_uses_this_turn:
                break

            # Turn the model's tool_use blocks back into the assistant message,
            # then append a user message with tool_result blocks.
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": t} for t in text_this_turn
                    ]
                    + [
                        {
                            "type": "tool_use",
                            "id": tu["id"],
                            "name": tu["name"],
                            "input": tu["input"],
                        }
                        for tu in tool_uses_this_turn
                    ],
                }
            )

            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses_this_turn:
                if ctx.on_tool_call:
                    ctx.on_tool_call(agent.name, tu["name"], tu["input"])
                try:
                    spec = registry.get(tu["name"])
                    result = spec.func(**tu["input"])
                    content = (
                        result
                        if isinstance(result, str)
                        else json.dumps(result, default=str)
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": content,
                        }
                    )
                except Exception as exc:  # surface errors to the model
                    log.exception("tool %s failed", tu["name"])
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "is_error": True,
                            "content": f"{type(exc).__name__}: {exc}",
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

        return AgentResult(
            text=last_text,
            tool_uses=all_tool_uses,
            stop_reason=stop_reason,
            tokens_in=total_in,
            tokens_out=total_out,
        )
