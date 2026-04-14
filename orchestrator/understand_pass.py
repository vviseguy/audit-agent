"""Understander pass — walks a cloned repo and invokes the agent per directory.

The caller (run_job) sets the sandbox root + run context before we start.
We pick directories worth annotating (has source code, not vendored), call
the engine once per directory, and persist `annotation` rows on the way.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from db import store as dbstore
from engine.budget import BudgetExceeded
from engine.loader import AgentSpec
from engine.runner import RunContext
from engine.sdk_runner import SDKEngine as Engine
from tools import runtime, sandbox

log = logging.getLogger(__name__)

SOURCE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb",
    ".php", ".c", ".h", ".cpp", ".cs", ".kt", ".swift",
}
IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", "target", "vendor", "out",
}


def _has_source(dir_path: Path) -> bool:
    for entry in dir_path.iterdir():
        if entry.is_file() and entry.suffix in SOURCE_EXTS:
            return True
    return False


def _pick_directories(root: Path, max_dirs: int) -> list[Path]:
    picked: list[Path] = []
    if _has_source(root):
        picked.append(root)
    for entry in sorted(root.rglob("*")):
        if not entry.is_dir():
            continue
        if any(part in IGNORED_DIRS for part in entry.relative_to(root).parts):
            continue
        if _has_source(entry):
            picked.append(entry)
        if len(picked) >= max_dirs:
            break
    return picked


def run(
    *,
    agent: AgentSpec,
    engine: Engine,
    eng_ctx: RunContext,
    rctx: runtime.RunContextHandle,
    repo_id: int,
    repo_clone_path: Path,
    max_dirs: int = 40,
) -> dict[str, int]:
    sandbox.set_root(repo_clone_path)
    runtime.set_run_context(rctx)
    runtime.set_current_agent(agent.name)

    dirs = _pick_directories(repo_clone_path, max_dirs=max_dirs)
    log.info("understander: %d directories to annotate", len(dirs))

    written = 0
    halted: str | None = None

    for d in dirs:
        rel = d.relative_to(repo_clone_path).as_posix() or "."
        user_msg = (
            f"Annotate the directory `{rel}`.\n\n"
            "Call `list_dir` on it, read 2-5 informative files, optionally `grep` for "
            "trust-boundary patterns, then call `write_claude_md` exactly once."
        )
        try:
            result = engine.run(agent, eng_ctx, user_msg, max_loops=6)
        except BudgetExceeded as exc:
            halted = exc.reason
            log.warning("understander halted: %s", exc)
            break

        anno = _extract_annotation(result.tool_uses)
        if anno:
            dbstore.upsert_annotation(
                rctx.conn,
                repo_id=repo_id,
                path=anno["dir_path"],
                summary=anno["summary"],
                trust_boundary=bool(anno.get("trust_boundary")),
                entry_point=bool(anno.get("entry_point")),
                dataflows=anno.get("dataflows") or [],
                claude_md_path=str((d / "CLAUDE.md").relative_to(repo_clone_path).as_posix()),
                last_run_id=rctx.run_id,
            )
            written += 1

    return {"dirs_seen": len(dirs), "annotations_written": written, "halted": halted or ""}


def _extract_annotation(tool_uses: list[dict]) -> dict | None:
    for tu in reversed(tool_uses):
        if tu.get("name") == "write_claude_md":
            return tu.get("input") or None
    return None
