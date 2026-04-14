"""Retrieve cross-source vulnerability-type context for the Ranker and Delver.

Pulls top-k hits from the CWE, OWASP Top 10, CAPEC, and ATT&CK collections in
one call so agents don't have to make four separate tool calls to ground a
single candidate in documented weakness knowledge.
"""

from __future__ import annotations

import json

from rag.vuln_type_context import retrieve_vuln_type_context as _retrieve
from tools.base import tool


@tool(
    name="retrieve_vuln_type_context",
    description=(
        "Fetch cross-source context about a type of vulnerability in one call. "
        "Queries the CWE taxonomy, OWASP Top 10, CAPEC attack patterns, and "
        "MITRE ATT&CK techniques using the given free-text `query`. If a "
        "`cwe_id` is supplied, the CWE entry is pinned to the top of the CWE "
        "results and CAPEC patterns that cross-reference that CWE are merged "
        "in. Returns a bundle: "
        "{cwe: [...], owasp: [...], capec: [...], attack: [...]}. "
        "Use this to ground severity/likelihood judgments (Ranker) and to "
        "author concrete exploit-flow narratives in draft issues (Delver). "
        "Each hit includes metadata like `top25` (CWE Top 25 membership), "
        "`rank` (OWASP rank), `likelihood`/`severity` (CAPEC), and `tactics` "
        "(ATT&CK)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Free-text description of the finding or weakness.",
            },
            "cwe_id": {
                "type": "string",
                "description": "Optional CWE id like 'CWE-89' to pin and cross-link.",
            },
            "k_per_source": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Top-k hits per collection (default 3).",
            },
        },
        "required": ["query"],
    },
)
def retrieve_vuln_type_context(
    query: str,
    cwe_id: str | None = None,
    k_per_source: int = 3,
) -> str:
    bundle = _retrieve(
        query=query,
        cwe_id=cwe_id or None,
        k_per_source=k_per_source,
    )
    return json.dumps(bundle, default=str)
