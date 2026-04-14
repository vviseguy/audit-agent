"""Batch promotion: draft_issue → real GitHub issue.

Runs on the host after a human approves a batch from the Draft Issues
page. Uses the project's issues-only PAT via `gh.client.GitHubClient`;
on any failure, halts the batch and reports which drafts failed so the
user can retry just those.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from db import store as dbstore
from gh.client import GitHubClient

log = logging.getLogger(__name__)


@dataclass
class PromotionOutcome:
    draft_issue_id: int
    success: bool
    github_issue_url: str | None
    error: str | None


def _resolve_issues_token(conn, project_id: int) -> tuple[str, str]:
    row = conn.execute(
        """
        SELECT gt.label, gt.secret_ref, gt.scope
        FROM project p JOIN github_token gt ON gt.id = p.issues_token_id
        WHERE p.id=?
        """,
        (project_id,),
    ).fetchone()
    if not row:
        raise RuntimeError(
            f"project {project_id} has no issues_token_id configured"
        )
    if row["scope"] not in ("issues_only", "read_and_issues"):
        raise RuntimeError(
            f"project {project_id} issues token scope is {row['scope']!r}; "
            "cannot promote"
        )
    secret = os.environ.get(row["secret_ref"], "")
    if not secret:
        raise RuntimeError(f"env var {row['secret_ref']} is empty")
    return row["label"], secret


def _resolve_repo_for_vuln(conn, vulnerability_id: int) -> tuple[str, str]:
    row = conn.execute(
        """
        SELECT r.owner, r.name FROM vulnerability v
        JOIN repo r ON r.id = v.repo_id
        WHERE v.id=?
        """,
        (vulnerability_id,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"no repo found for vulnerability {vulnerability_id}")
    return row["owner"], row["name"]


def _build_labels(conn, vulnerability_id: int, draft_severity: str | None) -> list[str]:
    """Assemble the label set for one promoted issue.

    We always include `audit-agent` so the issues are easy to filter out of
    the repo's triage view. Severity and CWE come from the vulnerability row
    when present — they're the two axes a triager actually sorts on.
    """
    labels: list[str] = ["audit-agent"]
    row = conn.execute(
        "SELECT cwe_id, impact, likelihood, priority FROM vulnerability WHERE id=?",
        (vulnerability_id,),
    ).fetchone()
    severity = (draft_severity or "").strip().lower()
    if not severity and row:
        impact = int(row["impact"] or 0)
        severity = {5: "critical", 4: "high", 3: "medium", 2: "low", 1: "info"}.get(impact, "")
    if severity:
        labels.append(f"severity:{severity}")
    if row and row["cwe_id"]:
        labels.append(str(row["cwe_id"]).lower())
    return labels


def promote_batch(
    conn,
    *,
    project_id: int,
    draft_issue_ids: list[int],
    approved_by: str,
    client_factory=GitHubClient,
) -> list[PromotionOutcome]:
    """Promote a batch of draft_issue rows into real GitHub issues.

    Halts on the first failure to keep the blast radius small. Returns a
    list of outcomes; the caller reports which succeeded and which failed.
    """
    _, token = _resolve_issues_token(conn, project_id)
    outcomes: list[PromotionOutcome] = []

    with client_factory(token) as client:
        for draft_id in draft_issue_ids:
            row = conn.execute(
                """
                SELECT id, vulnerability_id, title, body_md, severity, status
                FROM draft_issue
                WHERE id=? AND project_id=?
                """,
                (int(draft_id), project_id),
            ).fetchone()
            if not row:
                outcomes.append(PromotionOutcome(
                    draft_issue_id=int(draft_id),
                    success=False,
                    github_issue_url=None,
                    error="draft not found in this project",
                ))
                break
            if row["status"] != "draft":
                outcomes.append(PromotionOutcome(
                    draft_issue_id=int(draft_id),
                    success=False,
                    github_issue_url=None,
                    error=f"draft status is {row['status']!r}, not 'draft'",
                ))
                break

            owner, repo = _resolve_repo_for_vuln(conn, int(row["vulnerability_id"]))
            labels = _build_labels(
                conn,
                int(row["vulnerability_id"]),
                row["severity"] if "severity" in row.keys() else None,
            )
            try:
                resp = client.create_issue(
                    owner, repo,
                    title=row["title"],
                    body=row["body_md"],
                    labels=labels,
                )
            except Exception as exc:
                log.exception("create_issue failed for draft %s", draft_id)
                outcomes.append(PromotionOutcome(
                    draft_issue_id=int(draft_id),
                    success=False,
                    github_issue_url=None,
                    error=f"network: {exc}",
                ))
                break

            if resp.status_code not in (200, 201):
                outcomes.append(PromotionOutcome(
                    draft_issue_id=int(draft_id),
                    success=False,
                    github_issue_url=None,
                    error=f"github {resp.status_code}: {resp.text[:300]}",
                ))
                break

            issue_url = resp.json().get("html_url", "")
            conn.execute(
                """
                UPDATE draft_issue
                SET status='sent', github_issue_url=?, approved_by=?,
                    approved_at=CURRENT_TIMESTAMP, sent_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (issue_url, approved_by, int(draft_id)),
            )
            conn.execute(
                "UPDATE vulnerability SET status='issue_sent', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(row["vulnerability_id"]),),
            )
            dbstore.append_journal(
                conn,
                vulnerability_id=int(row["vulnerability_id"]),
                run_id=None,
                agent="system",
                action="issue_sent",
                payload={
                    "github_issue_url": issue_url,
                    "draft_issue_id": int(draft_id),
                    "labels": labels,
                },
            )
            outcomes.append(PromotionOutcome(
                draft_issue_id=int(draft_id),
                success=True,
                github_issue_url=issue_url,
                error=None,
            ))

    return outcomes
