"""Seed a demo project with realistic fake data so the PWA looks alive.

No API calls, no Semgrep, no Docker — just populates SQLite + ChromaDB
project_memory with ~30 vulnerabilities, their journal history, 6 draft
issues, 4 completed runs, and a few queued and past sessions so every
UI page has something to show.

Idempotent: re-running wipes the demo project only (not other projects)
and re-seeds it.

Usage:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --db ./data/audit.db --project demo
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import store as dbstore  # noqa: E402

DEMO_NAME = "juice-shop-demo"

# A small catalogue of realistic-looking findings across CWE families.
# Tuple: (path, line_start, line_end, cwe_id, title, short_desc,
#         impact, likelihood, status, effort_hours)
# effort_hours is the Ranker's agile-hours estimate for the Delver to scan
# the relevant attack surface — 0.5 trivial, 2 typical, 4+ involved, 8+ a day.
FINDINGS = [
    ("api/users.py", 42, 45, "CWE-89", "SQL injection in user search",
     "unparameterized SELECT built with f-string", 4, 5, "needs_delve", 2.0),
    ("api/auth.py", 18, 28, "CWE-287", "Weak JWT verification skips signature",
     "verify=False passed to decode()", 5, 3, "needs_delve", 4.0),
    ("api/files.py", 71, 78, "CWE-22", "Path traversal in file download",
     "user-controlled path joined with os.path.join", 4, 4, "needs_delve", 2.0),
    ("api/orders.py", 55, 60, "CWE-639", "IDOR on /orders/<id>",
     "no owner check before returning order", 4, 4, "delved", 3.0),
    ("api/admin.py", 12, 30, "CWE-285", "Admin endpoint missing auth",
     "route decorated without require_admin", 5, 4, "draft_issue", 4.0),
    ("api/register.py", 33, 40, "CWE-521", "Password policy missing",
     "no length/complexity check on signup", 2, 5, "low_priority", 0.5),
    ("api/search.py", 14, 18, "CWE-79", "Reflected XSS in search response",
     "query echoed into HTML without escaping", 3, 4, "needs_delve", 1.5),
    ("api/comments.py", 22, 30, "CWE-79", "Stored XSS in comment body",
     "raw markdown rendered without sanitize", 4, 4, "delved", 2.0),
    ("api/upload.py", 60, 75, "CWE-434", "Unrestricted file upload",
     "no mime/extension validation", 4, 4, "needs_delve", 3.0),
    ("api/deserialize.py", 8, 14, "CWE-502", "Insecure pickle.loads on request body",
     "pickle.loads called on untrusted input", 5, 3, "needs_delve", 6.0),
    ("api/xml_parser.py", 3, 12, "CWE-611", "XXE via lxml default parser",
     "resolve_entities left at default True", 4, 3, "low_priority", 2.0),
    ("api/redirect.py", 5, 11, "CWE-601", "Open redirect on /go",
     "redirects to ?next= without allowlist", 2, 5, "needs_delve", 0.5),
    ("api/webhook.py", 40, 55, "CWE-352", "CSRF on state-changing webhook",
     "no signature/origin check", 3, 4, "delved", 2.0),
    ("api/reset.py", 18, 30, "CWE-640", "Weak password reset token",
     "uses time.time() as seed, 4-digit code", 4, 3, "needs_delve", 3.0),
    ("api/rate_limit.py", 1, 8, "CWE-770", "No rate limiting on /login",
     "brute force trivially enabled", 3, 5, "needs_delve", 1.0),
    ("api/debug.py", 2, 12, "CWE-489", "Debug endpoint exposed in prod",
     "returns env vars on /debug", 4, 2, "low_priority", 0.5),
    ("services/payment.py", 90, 110, "CWE-840", "Business logic: negative quantity accepted",
     "qty < 0 reduces total but grants items", 4, 3, "needs_delve", 4.0),
    ("services/coupon.py", 22, 35, "CWE-840", "Coupon stacking not bounded",
     "same coupon applied N times", 2, 4, "low_priority", 2.0),
    ("services/mailer.py", 11, 19, "CWE-93", "Email header injection",
     "user-supplied name copied into From:", 2, 3, "false_positive", 1.0),
    ("services/session.py", 30, 45, "CWE-384", "Session fixation on login",
     "session id not rotated after auth", 3, 3, "needs_delve", 3.0),
    ("services/crypto.py", 5, 12, "CWE-327", "MD5 used for password hashing",
     "hashlib.md5 on signup", 5, 3, "delved", 2.0),
    ("services/logger.py", 44, 52, "CWE-532", "Secrets logged on error",
     "entire request body logged on 500", 3, 3, "low_priority", 1.0),
    ("services/db.py", 1, 10, "CWE-798", "Hardcoded DB credentials",
     "password literal in source", 4, 5, "draft_issue", 0.5),
    ("services/cache.py", 20, 30, "CWE-400", "Unbounded cache growth",
     "no eviction on in-memory dict", 2, 3, "low_priority", 1.0),
    ("views/admin.html", 1, 1, "CWE-693", "No CSP header set",
     "responses lack Content-Security-Policy", 2, 4, "needs_delve", 0.5),
    ("views/profile.html", 12, 16, "CWE-79", "DOM XSS via innerHTML",
     "user bio assigned to .innerHTML", 3, 4, "needs_delve", 1.5),
    ("infra/nginx.conf", 5, 9, "CWE-16", "Missing HSTS",
     "Strict-Transport-Security not set", 2, 4, "low_priority", 0.25),
    ("infra/nginx.conf", 12, 18, "CWE-16", "TLS 1.0 allowed",
     "ssl_protocols includes TLSv1", 3, 3, "low_priority", 0.5),
    ("tests/fixtures.py", 1, 5, "CWE-259", "Test fixture uses hardcoded API key",
     "likely-not-exploitable but leaks shape", 1, 2, "false_positive", 0.25),
    ("api/graphql.py", 100, 130, "CWE-1333", "ReDoS in regex validator",
     "catastrophic backtracking on crafted email", 3, 3, "needs_delve", 2.0),
]

ANNOTATIONS = [
    ("api", "HTTP entry points for the storefront. Trust boundary: every file here reads request data and is reachable from public traffic.",
     True, True),
    ("services", "Business logic: payment, mailer, session, crypto. Called by api/. Not directly reachable, but processes untrusted data forwarded from api/.",
     True, False),
    ("views", "Server-side rendered HTML templates. XSS sink surface.",
     True, False),
    ("infra", "Deployment configuration — nginx, docker-compose. Not runtime-reachable but controls TLS + headers.",
     False, False),
    ("tests", "Unit + integration tests. Not exploitable in prod.",
     False, False),
]

DELVER_RATIONALES = {
    "needs_delve": "Ranker routed for delve: priority ≥ 8 and plausible exploit path.",
    "delved": "Delver confirmed exploit scenario and wrote a draft issue.",
    "draft_issue": "Delver produced a draft issue; pending human review.",
    "low_priority": "Real finding but priority < 8; recorded not delved.",
    "false_positive": "Rule did not apply to the actual code on re-reading.",
}


def _clear_project(conn, project_id: int) -> None:
    # annotation/vulnerability/journal_entry all FK run(id) without cascade,
    # so we defer FK checks to commit time and delete in dependency order.
    conn.execute("PRAGMA defer_foreign_keys = ON")
    try:
        conn.execute("DELETE FROM journal_entry WHERE vulnerability_id IN (SELECT id FROM vulnerability WHERE project_id=?)", (project_id,))
        conn.execute("DELETE FROM draft_issue WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM vulnerability WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM annotation WHERE repo_id IN (SELECT id FROM repo WHERE project_id=?)", (project_id,))
        conn.execute("DELETE FROM run WHERE session_id IN (SELECT id FROM session WHERE project_id=?)", (project_id,))
        conn.execute("DELETE FROM session WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM repo WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM project WHERE id=?", (project_id,))
        conn.commit()
    finally:
        conn.execute("PRAGMA defer_foreign_keys = OFF")


def _ensure_cwes(conn, ids: list[str]) -> None:
    for cwe_id in ids:
        existing = dbstore.get_cwe(conn, cwe_id)
        if existing:
            continue
        dbstore.upsert_cwe(
            conn,
            [
                {
                    "id": cwe_id,
                    "name": f"{cwe_id} (demo)",
                    "short_desc": f"Auto-generated CWE row for demo data: {cwe_id}",
                    "detail": "",
                    "consequences": "",
                    "mitigations": "",
                    "parent_id": None,
                }
            ],
        )


def seed(db_path: str, project_name: str = DEMO_NAME) -> dict:
    conn = dbstore.init(db_path)
    # Wipe existing demo project.
    row = conn.execute("SELECT id FROM project WHERE name=?", (project_name,)).fetchone()
    if row:
        _clear_project(conn, int(row["id"]))

    # Tokens (labels only; secrets are env-ref'd elsewhere).
    read_token_id = conn.execute(
        "INSERT INTO github_token(label, secret_ref, scope, validated_at, validation_result) "
        "VALUES(?, ?, 'read_only', CURRENT_TIMESTAMP, ?)",
        (
            f"{project_name} read",
            "GITHUB_PAT_READ",
            json.dumps({"ok": True, "repos": [{"owner": "juice-shop", "name": "juice-shop", "read_ok": True, "write_blocked": True}]}),
        ),
    ).lastrowid
    issues_token_id = conn.execute(
        "INSERT INTO github_token(label, secret_ref, scope, validated_at, validation_result) "
        "VALUES(?, ?, 'issues_only', CURRENT_TIMESTAMP, ?)",
        (
            f"{project_name} issues",
            "GITHUB_PAT_ISSUES",
            json.dumps({"ok": True, "repos": [{"owner": "juice-shop", "name": "juice-shop", "read_ok": True, "write_blocked": True, "issue_scope_ok": True}]}),
        ),
    ).lastrowid

    project_id = conn.execute(
        "INSERT INTO project(name, default_risk_lens, daily_token_budget, per_session_pct_cap, "
        "create_issues, read_token_id, issues_token_id) "
        "VALUES(?, 'high_impact', 2000000, 30.0, 1, ?, ?)",
        (project_name, read_token_id, issues_token_id),
    ).lastrowid

    repo_id = conn.execute(
        "INSERT INTO repo(project_id, url, owner, name, branch, last_commit_sha, clone_path) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            "https://github.com/juice-shop/juice-shop",
            "juice-shop",
            "juice-shop",
            "master",
            "a1b2c3d4e5f6",
            "./data/clones/juice-shop",
        ),
    ).lastrowid

    # Sessions + runs spanning the last ~10 days.
    now = datetime.now()
    sessions: list[tuple[int, int, str]] = []
    for i, (stype, days_ago, status) in enumerate([
        ("understand", 10, "done"),
        ("rank", 9, "done"),
        ("delve", 8, "done"),
        ("rank", 5, "done"),
        ("delve", 2, "halted"),
    ]):
        sched = (now - timedelta(days=days_ago)).isoformat(sep=" ")
        session_id = conn.execute(
            "INSERT INTO session(project_id, type, risk_lens, interest_prompt, scheduled_for, "
            "session_pct_cap, status) VALUES(?, ?, 'high_impact', NULL, ?, 30.0, ?)",
            (project_id, stype, sched, status),
        ).lastrowid
        started = (now - timedelta(days=days_ago, minutes=-2)).isoformat(sep=" ")
        finished = (now - timedelta(days=days_ago, minutes=-45)).isoformat(sep=" ")
        tokens_in = random.randint(60_000, 180_000)
        tokens_out = random.randint(15_000, 40_000)
        halted_reason = "rate_limit_session_cap" if status == "halted" else None
        run_id = conn.execute(
            "INSERT INTO run(session_id, started_at, finished_at, status, tokens_in, tokens_out, "
            "cost_usd, pct_daily_budget_used, halted_reason) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, started, finished, "done" if status == "done" else "halted",
             tokens_in, tokens_out, tokens_in * 0.000003 + tokens_out * 0.000015,
             round((tokens_in + tokens_out) / 2_000_000 * 100, 2), halted_reason),
        ).lastrowid
        sessions.append((session_id, run_id, stype))

    # A queued and an in-future session too.
    conn.execute(
        "INSERT INTO session(project_id, type, risk_lens, interest_prompt, scheduled_for, "
        "session_pct_cap, status) VALUES(?, 'delve', 'ui_visible', 'focus on public routes', ?, 25.0, 'queued')",
        (project_id, (now + timedelta(hours=6)).isoformat(sep=" ")),
    )
    conn.execute(
        "INSERT INTO session(project_id, type, risk_lens, interest_prompt, scheduled_for, "
        "session_pct_cap, status) VALUES(?, 'rank', 'balanced', NULL, ?, 20.0, 'queued')",
        (project_id, (now + timedelta(days=1)).isoformat(sep=" ")),
    )

    # A resumed session: one session, two runs — first halted on budget,
    # second picked up later and completed. Gives the run-log a "resumed ×1"
    # block out of the box so the UI shows that state in the demo.
    resumed_sid = conn.execute(
        "INSERT INTO session(project_id, type, risk_lens, interest_prompt, scheduled_for, "
        "session_pct_cap, status) VALUES(?, 'delve', 'high_impact', NULL, ?, 20.0, 'done')",
        (project_id, (now - timedelta(days=3, hours=2)).isoformat(sep=" ")),
    ).lastrowid
    r1_start = (now - timedelta(days=3, hours=2)).isoformat(sep=" ")
    r1_end = (now - timedelta(days=3, hours=1, minutes=20)).isoformat(sep=" ")
    conn.execute(
        "INSERT INTO run(session_id, started_at, finished_at, status, tokens_in, tokens_out, "
        "cost_usd, pct_daily_budget_used, halted_reason) "
        "VALUES(?, ?, ?, 'halted', ?, ?, ?, ?, 'rate_limit_session_cap')",
        (resumed_sid, r1_start, r1_end, 110_000, 22_000,
         110_000 * 0.000003 + 22_000 * 0.000015, 6.6),
    )
    r2_start = (now - timedelta(days=2, hours=22)).isoformat(sep=" ")
    r2_end = (now - timedelta(days=2, hours=21, minutes=10)).isoformat(sep=" ")
    conn.execute(
        "INSERT INTO run(session_id, started_at, finished_at, status, tokens_in, tokens_out, "
        "cost_usd, pct_daily_budget_used, halted_reason) "
        "VALUES(?, ?, ?, 'done', ?, ?, ?, ?, NULL)",
        (resumed_sid, r2_start, r2_end, 95_000, 18_000,
         95_000 * 0.000003 + 18_000 * 0.000015, 5.6),
    )

    # Annotations.
    latest_run = sessions[0][1]
    for path, summary, boundary, entry in ANNOTATIONS:
        conn.execute(
            "INSERT INTO annotation(repo_id, path, claude_md_path, summary, trust_boundary, entry_point, "
            "dataflows_json, last_run_id) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (repo_id, path, f"{path}/CLAUDE.md", summary, int(boundary), int(entry),
             json.dumps([]), latest_run),
        )

    # CWEs — insert any we don't have yet.
    _ensure_cwes(conn, sorted({f[3] for f in FINDINGS}))

    # Vulnerabilities + journal entries.
    rank_run = next(r for s, r, t in sessions if t == "rank")
    delve_run = next(r for s, r, t in sessions if t == "delve")
    vuln_ids: list[int] = []
    for path, ls, le, cwe, title, short, impact, likelihood, status, effort_hours in FINDINGS:
        priority = impact * likelihood
        vuln_id = conn.execute(
            """
            INSERT INTO vulnerability(
                project_id, repo_id, path, line_start, line_end, cwe_id,
                title, short_desc, impact, likelihood, priority, effort_hours, status,
                first_seen_run_id, last_seen_run_id
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, repo_id, path, ls, le, cwe, title, short,
             impact, likelihood, priority, effort_hours, status, rank_run, delve_run),
        ).lastrowid
        vuln_ids.append(vuln_id)

        # Journal: ranked first, maybe delved, maybe drafted.
        dbstore.append_journal(
            conn,
            vulnerability_id=vuln_id,
            run_id=rank_run,
            agent="ranker",
            action="ranked",
            payload={
                "impact": impact,
                "likelihood": likelihood,
                "priority": priority,
                "effort_hours": effort_hours,
                "status": status,
                "rationale": DELVER_RATIONALES.get(status, ""),
            },
        )
        if status in ("delved", "draft_issue"):
            dbstore.append_journal(
                conn,
                vulnerability_id=vuln_id,
                run_id=delve_run,
                agent="delver",
                action="delved",
                payload={
                    "exploit_scenario": f"Attacker targets {path}:{ls} to exploit {cwe}.",
                    "remediation": "See draft issue for specific fix.",
                    "confidence": round(random.uniform(0.65, 0.95), 2),
                    "references": [cwe],
                },
            )

    # Draft issues for the six in draft_issue or delved status.
    draft_targets = [
        (i, status) for i, (_, _, _, _, _, _, _, _, status, _) in enumerate(FINDINGS)
        if status in ("draft_issue", "delved")
    ][:6]
    from gh.issue_formatter import render_issue_body

    for idx, _ in draft_targets:
        vuln_id = vuln_ids[idx]
        path, ls, le, cwe, title, short, impact, likelihood, _, _ = FINDINGS[idx]
        severity = {5: "critical", 4: "high", 3: "medium", 2: "low", 1: "info"}[impact]
        body = render_issue_body(
            title=title,
            severity=severity,
            cwe_id=cwe,
            cwe_name=f"{cwe} (demo)",
            path=path,
            line_start=ls,
            line_end=le,
            exploit_scenario=(
                f"An attacker hits `{path}:{ls}`. The short-desc says: \"{short}\". "
                "The reachable code path mishandles this input; see code excerpt below."
            ),
            remediation=(
                "Replace the unsafe call with a safe alternative specific to "
                f"the {cwe} family. The Understander's note on the enclosing "
                "module flags this as a trust boundary."
            ),
            code_excerpt=f"# {path}:{ls}..{le}\n# vulnerable snippet elided in demo\n",
            back_link=f"/vulnerabilities/{vuln_id}",
            confidence=0.8,
            references=[cwe],
        )
        draft_id = conn.execute(
            "INSERT INTO draft_issue(vulnerability_id, project_id, title, body_md, severity, status) "
            "VALUES(?, ?, ?, ?, ?, 'draft')",
            (vuln_id, project_id, title, body, severity),
        ).lastrowid
        dbstore.append_journal(
            conn,
            vulnerability_id=vuln_id,
            run_id=delve_run,
            agent="delver",
            action="issue_drafted",
            payload={"draft_issue_id": draft_id, "severity": severity, "title": title},
        )

    # Roll up token totals into the ledger for today so BudgetMeter has numbers.
    used_in = random.randint(180_000, 240_000)
    used_out = random.randint(30_000, 60_000)
    dbstore.add_tokens_today(conn, used_in, used_out, used_in * 0.000003 + used_out * 0.000015)

    return {
        "project_id": project_id,
        "repo_id": repo_id,
        "vulnerabilities": len(vuln_ids),
        "drafts": len(draft_targets),
        "sessions": len(sessions) + 2,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="./data/audit.db")
    ap.add_argument("--project", default=DEMO_NAME)
    args = ap.parse_args()
    random.seed(42)
    result = seed(args.db, args.project)
    print("seeded:", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
