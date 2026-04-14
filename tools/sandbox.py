"""Path sandbox for tools that read/write inside a cloned repo.

The sandbox is set per-run by the orchestrator. Tools call `resolve(path)`
to get an absolute path and get an error if the caller tried to escape.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path


class SandboxError(Exception):
    pass


_local = threading.local()


def set_root(root: str | Path) -> None:
    root = Path(root).resolve()
    if not root.is_dir():
        raise SandboxError(f"sandbox root does not exist: {root}")
    _local.root = root


def get_root() -> Path:
    root = getattr(_local, "root", None)
    if root is None:
        raise SandboxError(
            "no sandbox root set; orchestrator must call sandbox.set_root() first"
        )
    return root


def resolve(rel_path: str) -> Path:
    """Resolve a repo-relative path and verify it stays inside the sandbox root."""
    root = get_root()
    # Reject absolute paths outright so a confused tool call can't escape.
    if os.path.isabs(rel_path):
        raise SandboxError(f"absolute paths not allowed: {rel_path}")
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SandboxError(f"path escapes sandbox: {rel_path}") from exc
    return target
