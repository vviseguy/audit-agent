"""Append to an existing draft issue instead of creating a duplicate."""

from __future__ import annotations

import json

from db import store as dbstore
from tools.base import tool
from tools.runtime import get_run_context

_SEVERITIES = {"info", "low", "medium", "high", "critical"}


@tool(
    name="update_draft_issue",
    description=(
        "Update an existing draft issue: append an `Update` section to the "
        "body, optionally upgrade severity. Use this when a new finding is "
        "related to an existing draft (same CWE + same file region) — avoid "
        "creating duplicates."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "draft_issue_id": {"type": "integer", "minimum": 1},
            "append_section_title": {"type": "string", "minLength": 3, "maxLength": 100},
            "append_markdown": {"type": "string", "minLength": 10},
            "upgrade_severity_to": {"type": "string", "enum": sorted(_SEVERITIES)},
        },
        "required": ["draft_issue_id", "append_section_title", "append_markdown"],
    },
)
def update_draft_issue(
    draft_issue_id: int,
    append_section_title: str,
    append_markdown: str,
    upgrade_severity_to: str | None = None,
) -> str:
    rctx = get_run_context()
    conn = rctx.conn

    row = conn.execute(
        "SELECT id, vulnerability_id, body_md, severity, status FROM draft_issue "
        "WHERE id=? AND project_id=?",
        (int(draft_issue_id), rctx.project_id),
    ).fetchone()
    if not row:
        raise ValueError(f"draft_issue {draft_issue_id} not found in this project")
    if row["status"] != "draft":
        raise ValueError(
            f"draft_issue {draft_issue_id} has status {row['status']}, not 'draft'"
        )

    new_body = f"{row['body_md']}\n\n## {append_section_title}\n{append_markdown}\n"
    new_severity = upgrade_severity_to or row["severity"]
    conn.execute(
        "UPDATE draft_issue SET body_md=?, severity=?, updated_at=CURRENT_TIMESTAMP "
        "WHERE id=?",
        (new_body, new_severity, int(draft_issue_id)),
    )

    dbstore.append_journal(
        conn,
        vulnerability_id=int(row["vulnerability_id"]),
        run_id=rctx.run_id,
        agent=rctx.current_agent or "delver",
        action="issue_updated",
        payload={
            "draft_issue_id": int(draft_issue_id),
            "section": append_section_title,
            "severity": new_severity,
        },
    )
    return json.dumps({"draft_issue_id": int(draft_issue_id), "severity": new_severity})
