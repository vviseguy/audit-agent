"""Render draft_issue rows into the fixed Markdown format used for GitHub issues."""

from __future__ import annotations

SEVERITY_BADGE = {
    "info": "![info](https://img.shields.io/badge/severity-info-lightgrey)",
    "low": "![low](https://img.shields.io/badge/severity-low-yellow)",
    "medium": "![medium](https://img.shields.io/badge/severity-medium-orange)",
    "high": "![high](https://img.shields.io/badge/severity-high-red)",
    "critical": "![critical](https://img.shields.io/badge/severity-critical-darkred)",
}


def render_issue_body(
    *,
    title: str,
    severity: str,
    cwe_id: str,
    cwe_name: str,
    path: str,
    line_start: int,
    line_end: int,
    exploit_scenario: str,
    remediation: str,
    code_excerpt: str,
    back_link: str,
    confidence: float | None = None,
    references: list[str] | None = None,
) -> str:
    badge = SEVERITY_BADGE.get(severity.lower(), severity)
    refs = "\n".join(f"- {r}" for r in (references or [])) or "_(none)_"
    conf = f"{confidence:.2f}" if confidence is not None else "n/a"
    return (
        f"{badge}\n\n"
        f"**CWE:** [{cwe_id}](https://cwe.mitre.org/data/definitions/{cwe_id.split('-')[-1]}.html)"
        f" — {cwe_name}\n\n"
        f"**Location:** `{path}:{line_start}-{line_end}`\n\n"
        f"**Confidence:** {conf}\n\n"
        f"## Exploit scenario\n{exploit_scenario}\n\n"
        f"## Remediation\n{remediation}\n\n"
        f"## Code excerpt\n```\n{code_excerpt}\n```\n\n"
        f"## References\n{refs}\n\n"
        f"---\n_Tracked in audit PWA: {back_link}_"
    )
