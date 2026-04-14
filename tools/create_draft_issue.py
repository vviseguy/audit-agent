"""Delver creates a draft issue for a vulnerability. Never writes to GitHub directly."""

from __future__ import annotations

import json

from db import store as dbstore
from gh.issue_formatter import render_issue_body
from tools.base import tool
from tools.runtime import get_run_context

_SEVERITIES = {"info", "low", "medium", "high", "critical"}


@tool(
    name="create_draft_issue",
    description=(
        "Create a draft issue for a vulnerability. The issue is rendered into "
        "the project's fixed Markdown template and stored in the DB with "
        "status='draft'. A human must approve a batch from the UI before any "
        "GitHub issue is actually created. Call `retrieve_draft_issues` first "
        "if unsure whether a related draft already exists."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "vulnerability_id": {"type": "integer", "minimum": 1},
            "title": {"type": "string", "minLength": 3, "maxLength": 200},
            "severity": {"type": "string", "enum": sorted(_SEVERITIES)},
            "exploit_scenario": {"type": "string", "minLength": 10},
            "remediation": {"type": "string", "minLength": 10},
            "code_excerpt": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "references": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
            },
        },
        "required": [
            "vulnerability_id",
            "title",
            "severity",
            "exploit_scenario",
            "remediation",
            "code_excerpt",
        ],
    },
)
def create_draft_issue(
    vulnerability_id: int,
    title: str,
    severity: str,
    exploit_scenario: str,
    remediation: str,
    code_excerpt: str,
    confidence: float | None = None,
    references: list[str] | None = None,
) -> str:
    rctx = get_run_context()
    conn = rctx.conn

    vuln = conn.execute(
        "SELECT * FROM vulnerability WHERE id=? AND project_id=?",
        (int(vulnerability_id), rctx.project_id),
    ).fetchone()
    if not vuln:
        raise ValueError(f"vulnerability {vulnerability_id} not found in this project")

    cwe_row = dbstore.get_cwe(conn, vuln["cwe_id"]) if vuln["cwe_id"] else None
    cwe_name = (cwe_row or {}).get("name", "")

    body_md = render_issue_body(
        title=title,
        severity=severity,
        cwe_id=vuln["cwe_id"] or "CWE-20",
        cwe_name=cwe_name,
        path=vuln["path"],
        line_start=int(vuln["line_start"]),
        line_end=int(vuln["line_end"]),
        exploit_scenario=exploit_scenario,
        remediation=remediation,
        code_excerpt=code_excerpt,
        back_link=f"/vulnerabilities/{vulnerability_id}",
        confidence=confidence,
        references=references or [],
    )

    cur = conn.execute(
        """
        INSERT INTO draft_issue(
            vulnerability_id, project_id, title, body_md, severity, status
        ) VALUES(?, ?, ?, ?, ?, 'draft')
        """,
        (int(vulnerability_id), rctx.project_id, title, body_md, severity),
    )
    draft_id = int(cur.lastrowid)

    conn.execute(
        "UPDATE vulnerability SET status='draft_issue', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(vulnerability_id),),
    )
    dbstore.append_journal(
        conn,
        vulnerability_id=int(vulnerability_id),
        run_id=rctx.run_id,
        agent=rctx.current_agent or "delver",
        action="issue_drafted",
        payload={
            "draft_issue_id": draft_id,
            "severity": severity,
            "title": title,
            "confidence": confidence,
        },
    )
    return json.dumps({"draft_issue_id": draft_id})
