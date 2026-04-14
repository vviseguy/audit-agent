"""Import a project YAML into the DB.

Usage:
    python scripts/import_project.py projects/example.yaml

Safe to re-run: upserts project, github_token, and repo rows by their
natural keys. Does NOT delete rows that disappeared from the YAML — use
the UI for deletions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import store as dbstore  # noqa: E402


def _load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _upsert_token(conn, *, label: str, secret_ref: str, scope: str) -> int:
    row = conn.execute(
        "SELECT id FROM github_token WHERE label=? AND secret_ref=?",
        (label, secret_ref),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE github_token SET scope=? WHERE id=?",
            (scope, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO github_token(label, secret_ref, scope) VALUES(?, ?, ?)",
        (label, secret_ref, scope),
    )
    return int(cur.lastrowid)


def _upsert_project(
    conn,
    *,
    name: str,
    default_risk_lens: str,
    daily_token_budget: int,
    per_session_pct_cap: float,
    create_issues: bool,
    read_token_id: int | None,
    issues_token_id: int | None,
) -> int:
    row = conn.execute("SELECT id FROM project WHERE name=?", (name,)).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project
            SET default_risk_lens=?, daily_token_budget=?, per_session_pct_cap=?,
                create_issues=?, read_token_id=?, issues_token_id=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                default_risk_lens,
                daily_token_budget,
                per_session_pct_cap,
                1 if create_issues else 0,
                read_token_id,
                issues_token_id,
                row["id"],
            ),
        )
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO project(
            name, default_risk_lens, daily_token_budget, per_session_pct_cap,
            create_issues, read_token_id, issues_token_id
        ) VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            default_risk_lens,
            daily_token_budget,
            per_session_pct_cap,
            1 if create_issues else 0,
            read_token_id,
            issues_token_id,
        ),
    )
    return int(cur.lastrowid)


def _upsert_repo(
    conn,
    *,
    project_id: int,
    url: str,
    owner: str,
    name: str,
    branch: str,
) -> int:
    row = conn.execute(
        "SELECT id FROM repo WHERE project_id=? AND owner=? AND name=?",
        (project_id, owner, name),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE repo SET url=?, branch=? WHERE id=?",
            (url, branch, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO repo(project_id, url, owner, name, branch) VALUES(?, ?, ?, ?, ?)",
        (project_id, url, owner, name, branch),
    )
    return int(cur.lastrowid)


def import_project(yaml_path: Path, db_path: str) -> dict:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    conn = dbstore.init(db_path)

    read_token_id: int | None = None
    issues_token_id: int | None = None
    token_ids: dict[str, int] = {}
    for t in data.get("github_tokens", []) or []:
        tid = _upsert_token(
            conn,
            label=t["label"],
            secret_ref=t["secret_ref"],
            scope=t["scope"],
        )
        token_ids[t["label"]] = tid
        use_for = t.get("use_for")
        if use_for == "read":
            read_token_id = tid
        elif use_for == "issues":
            issues_token_id = tid

    project_id = _upsert_project(
        conn,
        name=data["name"],
        default_risk_lens=data.get("default_risk_lens", "balanced"),
        daily_token_budget=int(data.get("daily_token_budget", 2_000_000)),
        per_session_pct_cap=float(data.get("per_session_pct_cap", 30.0)),
        create_issues=bool(data.get("create_issues", False)),
        read_token_id=read_token_id,
        issues_token_id=issues_token_id,
    )

    repo_ids: list[int] = []
    for r in data.get("repos", []) or []:
        repo_ids.append(
            _upsert_repo(
                conn,
                project_id=project_id,
                url=r["url"],
                owner=r["owner"],
                name=r["name"],
                branch=r.get("branch", "main"),
            )
        )

    return {
        "project_id": project_id,
        "repo_ids": repo_ids,
        "token_ids": token_ids,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml_path", type=Path)
    args = ap.parse_args()

    cfg = _load_config()
    result = import_project(args.yaml_path, cfg["paths"]["db"])
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
