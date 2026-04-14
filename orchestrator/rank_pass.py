"""Ranker pass — runs Semgrep then invokes the Ranker agent in batches.

The agent's `rank_candidates_batch` tool is the answer sink: it writes
vulnerability rows + journal entries directly, so this pass just needs to
confirm the tool was called for every batch and surface halted state.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from engine.budget import BudgetExceeded
from engine.loader import AgentSpec
from engine.runner import RunContext
from engine.sdk_runner import SDKEngine as Engine
from scanner.semgrep_runner import Candidate, run_semgrep
from tools import runtime, sandbox

log = logging.getLogger(__name__)


def _chunks(items: list[Candidate], size: int) -> list[list[Candidate]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _candidates_as_json(batch: list[Candidate]) -> str:
    return json.dumps([asdict(c) for c in batch], ensure_ascii=False)


def run(
    *,
    agent: AgentSpec,
    engine: Engine,
    eng_ctx: RunContext,
    rctx: runtime.RunContextHandle,
    repo_id: int,
    repo_clone_path: Path,
    candidates: list[Candidate] | None = None,
) -> dict:
    sandbox.set_root(repo_clone_path)
    runtime.set_run_context(rctx)
    runtime.set_current_agent(agent.name)

    if candidates is None:
        candidates = run_semgrep(repo_clone_path)
    log.info("ranker: %d candidates from semgrep", len(candidates))

    batch_size = agent.batch_size or 15
    batches = _chunks(candidates, batch_size)

    halted: str | None = None
    batches_done = 0
    batches_missing_tool_call = 0

    for batch in batches:
        user_msg = (
            "Rank the following Semgrep candidates. Every candidate must appear "
            "in your `rank_candidates_batch` call. Batch JSON:\n\n"
            f"{_candidates_as_json(batch)}"
        )
        try:
            result = engine.run(agent, eng_ctx, user_msg, max_loops=8)
        except BudgetExceeded as exc:
            halted = exc.reason
            log.warning("ranker halted: %s", exc)
            break

        called = any(tu.get("name") == "rank_candidates_batch" for tu in result.tool_uses)
        if not called:
            batches_missing_tool_call += 1
            log.warning(
                "ranker batch %d: agent did not call rank_candidates_batch",
                batches_done,
            )
        batches_done += 1

    return {
        "candidates_seen": len(candidates),
        "batches_total": len(batches),
        "batches_done": batches_done,
        "batches_missing_tool_call": batches_missing_tool_call,
        "halted": halted or "",
    }
