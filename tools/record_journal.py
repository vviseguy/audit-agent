from __future__ import annotations

import json

from tools.base import tool
from tools.runtime import get_run_context


@tool(
    name="record_journal",
    description=(
        "Append a journal entry for an agent action. If vulnerability_id is omitted, "
        "the entry is project-level (e.g., 'finished understand pass')."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "note": {"type": "string"},
            "vulnerability_id": {"type": "integer"},
        },
        "required": ["action", "note"],
    },
)
def record_journal(
    action: str,
    note: str,
    vulnerability_id: int | None = None,
) -> str:
    rctx = get_run_context()
    jid = rctx.append_journal(
        vulnerability_id=vulnerability_id,
        agent=rctx.current_agent,
        action=action,
        payload={"note": note},
    )
    return json.dumps({"journal_id": jid})
