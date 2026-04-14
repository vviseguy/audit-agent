"""Pre-flight validator for GitHub tokens.

Runs three checks against every repo in a project:
  1. READ:   GET contents/ must succeed.
  2. NO-WRITE: PUT contents/.audit-agent-write-probe must FAIL (403/404/422).
               If it succeeds, the token is over-scoped and the UI blocks
               the session with a red banner telling the user to downgrade.
  3. ISSUES (optional): if the project has create_issues=true and the token
               is intended for issues, we record whether issues scope looks
               present. We don't actually create a test issue — instead we
               check the X-OAuth-Scopes header on the repo GET for classic
               PATs, and the repo permissions for fine-grained PATs.

Results are serialized to JSON and stored on `github_token.validation_result`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from gh.client import GitHubClient

PROBE_PATH = ".audit-agent-write-probe"


@dataclass
class RepoCheck:
    owner: str
    name: str
    read_ok: bool
    write_blocked: bool
    issue_scope_ok: bool | None
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "name": self.name,
            "read_ok": self.read_ok,
            "write_blocked": self.write_blocked,
            "issue_scope_ok": self.issue_scope_ok,
            "notes": self.notes,
        }


@dataclass
class ValidationResult:
    token_label: str
    scope: str            # 'read_only' | 'read_and_issues' | 'issues_only'
    intended_for_issues: bool
    repos: list[RepoCheck]
    identity_login: str | None = None
    identity_ok: bool = False
    unlinked: bool = False  # True when no repos are linked yet — identity-only check

    @property
    def ok(self) -> bool:
        # Unlinked tokens are "ok" if identity succeeded — there's nothing else
        # to probe until they're bound to a project. The UI treats this as a
        # tentative green so the user knows the PAT at least works.
        if self.unlinked:
            return self.identity_ok
        if not self.repos:
            return False
        for r in self.repos:
            if not r.read_ok or not r.write_blocked:
                return False
            if self.intended_for_issues and r.issue_scope_ok is False:
                return False
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "token_label": self.token_label,
            "scope": self.scope,
            "intended_for_issues": self.intended_for_issues,
            "ok": self.ok,
            "unlinked": self.unlinked,
            "identity_login": self.identity_login,
            "identity_ok": self.identity_ok,
            "repos": [r.as_dict() for r in self.repos],
        }


def _resolve_secret(secret_ref: str) -> str:
    val = os.environ.get(secret_ref, "")
    if not val:
        raise RuntimeError(
            f"env var {secret_ref} is empty; set it before validating the token"
        )
    return val


def _check_read(client: GitHubClient, owner: str, name: str, notes: list[str]) -> bool:
    try:
        resp = client.get_repo_contents(owner, name)
    except httpx.HTTPError as exc:
        notes.append(f"read error: {exc}")
        return False
    if resp.status_code == 200:
        return True
    notes.append(f"read returned {resp.status_code}: {resp.text[:200]}")
    return False


def _check_write_blocked(
    client: GitHubClient, owner: str, name: str, notes: list[str]
) -> bool:
    try:
        resp = client.probe_put_content(owner, name, PROBE_PATH)
    except httpx.HTTPError as exc:
        notes.append(f"write probe network error (treated as blocked): {exc}")
        return True
    if resp.status_code in (403, 404, 422):
        return True
    if resp.status_code == 401:
        notes.append("write probe returned 401 — token likely has no repo scope at all")
        return True
    notes.append(
        f"WRITE PROBE DID NOT FAIL SAFELY: status={resp.status_code}. "
        "Token is over-scoped for 'read-only' use."
    )
    return False


def _check_issue_scope(
    client: GitHubClient, owner: str, name: str, notes: list[str]
) -> bool | None:
    try:
        resp = client.get_repo(owner, name)
    except httpx.HTTPError as exc:
        notes.append(f"repo get error: {exc}")
        return False
    if resp.status_code != 200:
        notes.append(f"repo get returned {resp.status_code}")
        return False
    classic_scopes = resp.headers.get("X-OAuth-Scopes", "")
    if classic_scopes:
        scopes = {s.strip() for s in classic_scopes.split(",") if s.strip()}
        if "repo" in scopes or "public_repo" in scopes:
            return True
        notes.append(f"classic PAT scopes {scopes} do not include repo/public_repo")
        return False
    # Fine-grained PAT: permissions live on the repo body.
    perms = (resp.json().get("permissions") or {})
    if perms.get("push") or perms.get("maintain") or perms.get("admin"):
        notes.append("fine-grained PAT has write/maintain/admin — over-scoped")
        return True  # it CAN open issues, but over-scoped will fail write-blocked
    # Without explicit permission info we can't prove issue scope; return None.
    return None


def validate_token_for_repos(
    *,
    token_label: str,
    secret_ref: str,
    scope: str,
    repos: list[tuple[str, str]],
    intended_for_issues: bool,
) -> ValidationResult:
    """Run read + no-write + issue-scope checks for every repo."""
    token = _resolve_secret(secret_ref)
    out_repos: list[RepoCheck] = []
    with GitHubClient(token) as client:
        for owner, name in repos:
            notes: list[str] = []
            read_ok = _check_read(client, owner, name, notes)
            write_blocked = _check_write_blocked(client, owner, name, notes)
            if intended_for_issues:
                issue_ok = _check_issue_scope(client, owner, name, notes)
            else:
                issue_ok = None
            out_repos.append(
                RepoCheck(
                    owner=owner,
                    name=name,
                    read_ok=read_ok,
                    write_blocked=write_blocked,
                    issue_scope_ok=issue_ok,
                    notes=notes,
                )
            )
    return ValidationResult(
        token_label=token_label,
        scope=scope,
        intended_for_issues=intended_for_issues,
        repos=out_repos,
    )


def validate_token_global(
    *,
    token_label: str,
    secret_ref: str,
    scope: str,
    repos: list[tuple[str, str]],
    intended_for_issues: bool,
) -> ValidationResult:
    """Same as validate_token_for_repos, but also runs an identity check so
    tokens with no linked repos still return a meaningful result that the
    UI can stamp with 'last checked'."""
    token = _resolve_secret(secret_ref)
    out_repos: list[RepoCheck] = []
    identity_ok = False
    identity_login: str | None = None
    with GitHubClient(token) as client:
        try:
            ident = client.get_user()
            if ident.status_code == 200:
                identity_ok = True
                identity_login = (ident.json() or {}).get("login")
        except httpx.HTTPError:
            identity_ok = False
        for owner, name in repos:
            notes: list[str] = []
            read_ok = _check_read(client, owner, name, notes)
            write_blocked = _check_write_blocked(client, owner, name, notes)
            if intended_for_issues:
                issue_ok = _check_issue_scope(client, owner, name, notes)
            else:
                issue_ok = None
            out_repos.append(
                RepoCheck(
                    owner=owner,
                    name=name,
                    read_ok=read_ok,
                    write_blocked=write_blocked,
                    issue_scope_ok=issue_ok,
                    notes=notes,
                )
            )
    return ValidationResult(
        token_label=token_label,
        scope=scope,
        intended_for_issues=intended_for_issues,
        repos=out_repos,
        identity_login=identity_login,
        identity_ok=identity_ok,
        unlinked=len(repos) == 0,
    )


def store_validation_result(conn, token_id: int, result: ValidationResult) -> None:
    conn.execute(
        """
        UPDATE github_token
        SET validated_at=CURRENT_TIMESTAMP, validation_result=?
        WHERE id=?
        """,
        (json.dumps(result.as_dict()), int(token_id)),
    )


def store_identity_failure(conn, token_id: int, error: str) -> None:
    """Stamp validated_at with a failure payload so the UI still shows
    when we last tried. Used when the env var is missing or the identity
    check itself couldn't run."""
    payload = {
        "ok": False,
        "unlinked": True,
        "identity_ok": False,
        "repos": [],
        "error": error,
    }
    conn.execute(
        """
        UPDATE github_token
        SET validated_at=CURRENT_TIMESTAMP, validation_result=?
        WHERE id=?
        """,
        (json.dumps(payload), int(token_id)),
    )
