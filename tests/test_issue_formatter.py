"""The Delver always writes into draft_issue; the rendered body is what
ends up on GitHub after human approval, so the template must be stable."""

from __future__ import annotations

from gh.issue_formatter import render_issue_body


def _sample() -> dict:
    return dict(
        title="SQL injection in /users search",
        severity="high",
        cwe_id="CWE-89",
        cwe_name="Improper Neutralization of Special Elements used in an SQL Command",
        path="api/users.py",
        line_start=42,
        line_end=45,
        exploit_scenario="Attacker supplies `' OR 1=1 --` in the q param.",
        remediation="Use parameterized queries via sqlalchemy.text() with bindparams.",
        code_excerpt='cursor.execute(f"SELECT * FROM users WHERE name LIKE \'%{q}%\'")',
        back_link="http://localhost:3000/vulnerabilities/31",
        confidence=0.92,
        references=["https://owasp.org/Top10/A03_2021-Injection/"],
    )


def test_render_contains_required_sections():
    body = render_issue_body(**_sample())
    assert "**CWE:**" in body
    assert "CWE-89" in body
    assert "cwe.mitre.org/data/definitions/89.html" in body
    assert "## Exploit scenario" in body
    assert "## Remediation" in body
    assert "## Code excerpt" in body
    assert "## References" in body
    assert "audit PWA" in body


def test_severity_badge_maps_known_levels():
    body = render_issue_body(**_sample())
    assert "badge/severity-high-red" in body


def test_confidence_is_formatted_to_two_places():
    body = render_issue_body(**_sample())
    assert "**Confidence:** 0.92" in body


def test_missing_references_renders_none_placeholder():
    args = _sample()
    args["references"] = None
    body = render_issue_body(**args)
    assert "_(none)_" in body


def test_code_excerpt_is_fenced():
    body = render_issue_body(**_sample())
    assert "```\ncursor.execute" in body
