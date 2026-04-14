from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server
from claude_agent_sdk.types import McpSdkServerConfig

from engine import registry

log = logging.getLogger(__name__)

MCP_SERVER_NAME = "audit_tools"


def _make_handler(spec: registry.ToolSpec):
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            # Our tools are sync and may block on file I/O or subprocess
            # (semgrep, chromadb). Run them off the event loop so the SDK
            # stays responsive to streaming messages.
            result = await asyncio.to_thread(spec.func, **args)
        except Exception as exc:
            log.exception("tool %s raised", spec.name)
            return {
                "isError": True,
                "content": [
                    {"type": "text", "text": f"{type(exc).__name__}: {exc}"}
                ],
            }
        text = result if isinstance(result, str) else json.dumps(result, default=str)
        return {"content": [{"type": "text", "text": text}]}

    return handler


def build_mcp_server(tool_names: tuple[str, ...] | list[str]) -> McpSdkServerConfig:
    """Bundle the requested registry tools into an in-process MCP server.

    Claude Code will discover these tools over stdio and call back into this
    Python process when the model invokes them. Tool names appear to the
    model as `mcp__audit_tools__<registered_name>`.
    """
    tools: list[SdkMcpTool] = []
    for name in tool_names:
        spec = registry.get(name)
        tools.append(
            SdkMcpTool(
                name=spec.name,
                description=spec.description,
                input_schema=spec.input_schema,
                handler=_make_handler(spec),
            )
        )
    return create_sdk_mcp_server(name=MCP_SERVER_NAME, version="1.0.0", tools=tools)


def mcp_tool_name(tool_name: str) -> str:
    return f"mcp__{MCP_SERVER_NAME}__{tool_name}"
