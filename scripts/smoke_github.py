"""Offline smoke test for the GitHub token validator + batch promotion.

No network: swaps gh.client.GitHubClient for a stub that answers with
canned responses, so we can verify the validator's logic and the
promotion pipeline without a real PAT.

Run with:
    python scripts/smoke_github.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import store as dbstore  # noqa: E402
from gh import promote, token_validator  # noqa: E402


@dataclass
class _StubResp:
    status_code: int
    _json: dict | None = None
    text: str = ""
    headers: dict | None = None

    def json(self) -> dict:
        return self._json or {}


class _ReadOnlyClient:
    """Simulates a fine-grained read-only PAT.

    - contents GET → 200
    - contents PUT → 403
    - repo GET → 200 with permissions={pull: True}
    - issues POST → 403 (we never call this with a read-only client)
    """

    def __init__(self, token: str, *, timeout: float = 20.0) -> None:
        self.token = token

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def close(self):
        pass

    def get_repo_contents(self, owner, repo, path=""):
        return _StubResp(status_code=200, _json=[], text="")

    def probe_put_content(self, owner, repo, path):
        return _StubResp(status_code=403, text="forbidden")

    def get_repo(self, owner, repo):
        return _StubResp(
            status_code=200,
            _json={"permissions": {"pull": True, "push": False}},
            headers={},
        )

    def create_issue(self, owner, repo, *, title, body, labels=None):
        return _StubResp(status_code=403, text="no issue scope")


class _OverScopedClient(_ReadOnlyClient):
    """Classic PAT with repo scope — write probe succeeds, which is bad."""

    def probe_put_content(self, owner, repo, path):
        return _StubResp(status_code=201, text="written (BAD)")


class _IssuesClient:
    """Fine-grained PAT with issues scope only — creates issues successfully."""

    def __init__(self, token, *, timeout=20.0):
        self.token = token
        self.created: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def close(self):
        pass

    def create_issue(self, owner, repo, *, title, body, labels=None):
        idx = len(self.created) + 1001
        self.created.append(
            {"owner": owner, "repo": repo, "title": title, "labels": labels or []}
        )
        return _StubResp(
            status_code=201,
            _json={"html_url": f"https://github.com/{owner}/{repo}/issues/{idx}"},
        )


def _seed_db(db_path: Path):
    dbstore.init(db_path)
    conn = dbstore.connect(db_path)
    dbstore.upsert_cwe(
        conn,
        [{"id": "CWE-89", "name": "SQL Injection", "short_desc": "", "detail": "",
          "consequences": "", "mitigations": "", "parent_id": None}],
    )
    conn.execute(
        "INSERT INTO github_token(label, secret_ref, scope) "
        "VALUES('read','GITHUB_PAT_READ','read_only')"
    )
    conn.execute(
        "INSERT INTO github_token(label, secret_ref, scope) "
        "VALUES('issues','GITHUB_PAT_ISSUES','issues_only')"
    )
    conn.execute(
        "INSERT INTO project(name, default_risk_lens, read_token_id, issues_token_id, create_issues) "
        "VALUES('smoke','balanced',1,2,1)"
    )
    conn.execute(
        "INSERT INTO repo(project_id, url, owner, name) "
        "VALUES(1,'https://example.invalid/smoke/repo','smoke','repo')"
    )
    conn.execute(
        """
        INSERT INTO vulnerability(
            project_id, repo_id, path, line_start, line_end, cwe_id, title, short_desc,
            impact, likelihood, priority, status
        ) VALUES(1, 1, 'app.py', 5, 5, 'CWE-89',
                 'SQL injection', 'unparameterized SELECT', 4, 4, 16, 'draft_issue')
        """
    )
    conn.execute(
        """
        INSERT INTO draft_issue(vulnerability_id, project_id, title, body_md, severity, status)
        VALUES(1, 1, 'SQL injection in handler', '# body\ncontent here', 'high', 'draft')
        """
    )
    return conn


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_gh_"))
    db_path = tmp / "audit.db"
    conn = _seed_db(db_path)

    os.environ["GITHUB_PAT_READ"] = "ghp_fakereadonly"
    os.environ["GITHUB_PAT_ISSUES"] = "ghp_fakeissues"

    # 1) Read-only token validates clean: read ok, write blocked.
    import gh.token_validator as tv_mod
    tv_mod.GitHubClient = _ReadOnlyClient  # type: ignore
    result = token_validator.validate_token_for_repos(
        token_label="read",
        secret_ref="GITHUB_PAT_READ",
        scope="read_only",
        repos=[("smoke", "repo")],
        intended_for_issues=False,
    )
    print("read-only validation:", result.as_dict())
    assert result.ok, "expected read-only token to validate clean"
    token_validator.store_validation_result(conn, 1, result)

    # 2) Over-scoped classic PAT: write probe succeeds → validation must fail.
    tv_mod.GitHubClient = _OverScopedClient  # type: ignore
    bad = token_validator.validate_token_for_repos(
        token_label="read",
        secret_ref="GITHUB_PAT_READ",
        scope="read_only",
        repos=[("smoke", "repo")],
        intended_for_issues=False,
    )
    print("over-scoped validation:", bad.as_dict())
    assert not bad.ok, "expected over-scoped token to FAIL validation"
    assert not bad.repos[0].write_blocked
    print("over-scoped failure correctly flagged")

    # 3) Promotion: issues client creates a real issue, draft → sent.
    clients_made: list[_IssuesClient] = []

    def _factory(token, *, timeout=20.0):
        c = _IssuesClient(token, timeout=timeout)
        clients_made.append(c)
        return c

    outcomes = promote.promote_batch(
        conn,
        project_id=1,
        draft_issue_ids=[1],
        approved_by="tester",
        client_factory=_factory,
    )
    assert clients_made, "promote_batch did not instantiate the issues client"
    created = clients_made[0].created
    assert created, "no issues created"
    labels_sent = created[0]["labels"]
    print("labels sent:", labels_sent)
    assert "audit-agent" in labels_sent
    assert "severity:high" in labels_sent
    assert "cwe-89" in labels_sent
    print("promotion outcomes:", [o.__dict__ for o in outcomes])
    assert len(outcomes) == 1 and outcomes[0].success
    assert outcomes[0].github_issue_url

    draft = conn.execute("SELECT status, github_issue_url FROM draft_issue WHERE id=1").fetchone()
    vuln = conn.execute("SELECT status FROM vulnerability WHERE id=1").fetchone()
    journal = conn.execute(
        "SELECT agent, action FROM journal_entry ORDER BY id"
    ).fetchall()
    print("draft after:", dict(draft))
    print("vuln after:", dict(vuln))
    print("journal:", [dict(j) for j in journal])

    assert draft["status"] == "sent"
    assert vuln["status"] == "issue_sent"
    assert any(j["action"] == "issue_sent" for j in journal)
    print("GITHUB PHASE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
