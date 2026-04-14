"""Similarity search over this project's past vulnerabilities and journal entries."""

from __future__ import annotations

import json

from rag.project_memory import query_similar
from tools.base import tool
from tools.runtime import get_run_context


@tool(
    name="retrieve_similar_vulnerabilities",
    description=(
        "Semantic search over this project's past vulnerabilities and journal "
        "entries (scoped by project_id). Use to check if a finding has already "
        "been investigated, to link related vulnerabilities, or to reuse past "
        "remediation reasoning. Returns top-k hits with document text, "
        "vulnerability_id, cwe_id, path, and distance."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "minimum": 1, "maximum": 10},
            "cwe_id": {"type": "string"},
        },
        "required": ["query"],
    },
)
def retrieve_similar_vulnerabilities(
    query: str, k: int = 5, cwe_id: str | None = None
) -> str:
    rctx = get_run_context()
    hits = query_similar(
        project_id=rctx.project_id,
        query_text=query,
        k=max(1, min(k, 10)),
        cwe_id=cwe_id or None,
    )
    return json.dumps({"results": hits}, default=str)
