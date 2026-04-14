"""Claude Code-backed engine. Drop-in replacement for engine.runner.Engine.

Instead of calling the Anthropic Messages API directly, this runner drives
the Claude Code CLI through the claude-agent-sdk. Our registered tools are
exposed as an in-process MCP server via engine.tool_bridge, so the CLI
calls back into this Python process when the model invokes read_file,
semgrep_scan, retrieve_cwe, etc.

The engine keeps its existing synchronous interface — each call opens a
one-shot `query()` session, drains the async message stream, and returns
an AgentResult so orchestrator/run_job.py and the pass modules don't need
to change.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from engine.loader import AgentSpec
from engine.runner import AgentResult, RunContext
from engine.tool_bridge import MCP_SERVER_NAME, build_mcp_server, mcp_tool_name

log = logging.getLogger(__name__)


class SDKEngine:
    """Drives Claude Code via claude-agent-sdk using the same interface as Engine."""

    def __init__(self, prompts_base: Path) -> None:
        self.prompts_base = Path(prompts_base)

    def run(
        self,
        agent: AgentSpec,
        ctx: RunContext,
        user_message: str,
        max_loops: int = 8,
    ) -> AgentResult:
        ctx.guard.check(agent.name)

        mcp_server = build_mcp_server(agent.tools)
        allowed = [mcp_tool_name(t) for t in agent.tools]

        system_text = agent.load_system_prompt(self.prompts_base.parent)
        extra = "\n\n".join(
            b.get("text", "")
            for b in ctx.extra_system_blocks
            if isinstance(b, dict) and b.get("type") == "text"
        )
        full_system = system_text + (("\n\n" + extra) if extra else "")

        opts = ClaudeAgentOptions(
            system_prompt=full_system,
            model=agent.model,
            max_turns=max_loops,
            mcp_servers={MCP_SERVER_NAME: mcp_server},
            allowed_tools=allowed,
            permission_mode="bypassPermissions",
        )

        return asyncio.run(self._run_async(agent, ctx, user_message, opts))

    async def _run_async(
        self,
        agent: AgentSpec,
        ctx: RunContext,
        user_message: str,
        opts: ClaudeAgentOptions,
    ) -> AgentResult:
        text_chunks: list[str] = []
        all_tool_uses: list[dict[str, Any]] = []
        tokens_in = 0
        tokens_out = 0
        stop_reason = ""

        async for msg in query(prompt=user_message, options=opts):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_chunks.append(block.text)
                        if ctx.on_text:
                            ctx.on_text(agent.name, block.text)
                    elif isinstance(block, ToolUseBlock):
                        # Claude Code reports MCP tools as mcp__<server>__<tool>.
                        # Strip the prefix so orchestrator callers can match on
                        # the bare registered name.
                        bare = block.name
                        prefix = f"mcp__{MCP_SERVER_NAME}__"
                        if bare.startswith(prefix):
                            bare = bare[len(prefix):]
                        all_tool_uses.append(
                            {
                                "id": block.id,
                                "name": bare,
                                "input": block.input,
                            }
                        )
                        if ctx.on_tool_call:
                            ctx.on_tool_call(agent.name, bare, block.input)
            elif isinstance(msg, ResultMessage):
                usage = msg.usage or {}
                tokens_in = (
                    (usage.get("input_tokens") or 0)
                    + (usage.get("cache_read_input_tokens") or 0)
                    + (usage.get("cache_creation_input_tokens") or 0)
                )
                tokens_out = usage.get("output_tokens") or 0
                stop_reason = getattr(msg, "subtype", "") or ""

        ctx.guard.record(agent.name, tokens_in, tokens_out)

        return AgentResult(
            text="\n".join(text_chunks),
            tool_uses=all_tool_uses,
            stop_reason=stop_reason,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
