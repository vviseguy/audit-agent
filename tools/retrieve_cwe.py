from __future__ import annotations

import json

from rag.chroma_client import CWE_COLLECTION, get_chroma
from tools.base import tool

_MAX_DOCS = 5


@tool(
    name="retrieve_cwe",
    description=(
        "Semantic search over the CWE taxonomy. Returns the top-k CWE entries "
        "most related to a free-text query. Use this to confirm a CWE id fits a "
        "finding or to discover the right CWE family for a pattern."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
)
def retrieve_cwe(query: str, k: int = 5) -> str:
    k = max(1, min(k, _MAX_DOCS))
    coll = get_chroma().get_or_create_collection(CWE_COLLECTION)
    res = coll.query(query_texts=[query], n_results=k)
    out: list[dict] = []
    if res.get("ids") and res["ids"][0]:
        for i, cid in enumerate(res["ids"][0]):
            md = res["metadatas"][0][i] or {}
            doc = res["documents"][0][i] or ""
            out.append(
                {
                    "cwe_id": cid,
                    "name": md.get("name", ""),
                    "excerpt": doc[:800],
                }
            )
    return json.dumps({"results": out})
