"""List this project's pending draft issues so the Delver can update instead of duplicating."""

from __future__ import annotations

import json

from tools.base import tool
from tools.runtime import get_run_context


@tool(
    name="retrieve_draft_issues",
    description=(
        "Return this project's open draft issues (status='draft'). Use before "
        "creating a new draft to check if a related one already exists — if so, "
        "prefer calling `update_draft_issue` to append context rather than "
        "creating a duplicate. Returns id, vulnerability_id, title, severity, status."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
    },
)
def retrieve_draft_issues(limit: int = 20) -> str:
    rctx = get_run_context()
    limit = max(1, min(int(limit), 100))
    rows = rctx.conn.execute(
        """
        SELECT id, vulnerability_id, title, severity, status
        FROM draft_issue
        WHERE project_id=? AND status='draft'
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (rctx.project_id, limit),
    ).fetchall()
    return json.dumps({"results": [dict(r) for r in rows]})
