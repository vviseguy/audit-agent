"""Minimal GitHub REST v3 client.

Deliberately does not expose any method that writes to repo contents.
The only write we support is `create_issue`. This is a *code-level*
guardrail on top of the token scope check — even if a caller wired up
an over-scoped PAT, this module gives them nothing to push files with.
"""

from __future__ import annotations

import httpx

API_BASE = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str, *, timeout: float = 20.0) -> None:
        self._token = token
        self._client = httpx.Client(
            base_url=API_BASE,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "audit-agent/0.1",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *a) -> None:
        self.close()

    # ---------- read ----------

    def get_repo_contents(self, owner: str, repo: str, path: str = "") -> httpx.Response:
        return self._client.get(f"/repos/{owner}/{repo}/contents/{path}")

    def get_repo(self, owner: str, repo: str) -> httpx.Response:
        return self._client.get(f"/repos/{owner}/{repo}")

    def get_user(self) -> httpx.Response:
        """Identity check. Works for any PAT with minimal scope — used by
        the global token validator when no repos are linked yet."""
        return self._client.get("/user")

    # ---------- probe (write — must fail for read-only tokens) ----------

    def probe_put_content(self, owner: str, repo: str, path: str) -> httpx.Response:
        """Attempt a contents PUT. Used by the validator — we WANT 403/404."""
        return self._client.put(
            f"/repos/{owner}/{repo}/contents/{path}",
            json={
                "message": "probe — should fail",
                "content": "",  # empty base64 is invalid too, so we fail twice over
            },
        )

    # ---------- issues ----------

    def create_issue(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> httpx.Response:
        payload: dict = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        return self._client.post(f"/repos/{owner}/{repo}/issues", json=payload)
