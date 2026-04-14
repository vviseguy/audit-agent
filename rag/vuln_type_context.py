"""Unified vulnerability-type context retrieval.

Queries the four type-of-vulnerability collections in ChromaDB and returns a
structured bundle the Ranker and Delver agents can paste into their prompts:

  - cwe    : entries from the CWE taxonomy (includes ``top25`` metadata flag)
  - owasp  : OWASP Top 10 categories
  - capec  : CAPEC attack patterns (exploit flow, prerequisites)
  - attack : MITRE ATT&CK techniques (post-exploitation tactics)

If ``cwe_id`` is provided, CAPEC results are augmented with patterns whose
embedded text mentions that CWE id, which catches cross-references that a
pure semantic search over ``query`` might miss.
"""

from __future__ import annotations

from typing import Any

from rag.chroma_client import (
    ATTACK_COLLECTION,
    CAPEC_COLLECTION,
    CWE_COLLECTION,
    OWASP_COLLECTION,
    get_chroma,
)


def _unpack(res: dict, excerpt_chars: int = 800) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not res.get("ids") or not res["ids"][0]:
        return out
    ids = res["ids"][0]
    docs = res.get("documents", [[]])[0] or [""] * len(ids)
    metas = res.get("metadatas", [[]])[0] or [{}] * len(ids)
    dists = res.get("distances", [[]])[0] or [None] * len(ids)
    for i, doc_id in enumerate(ids):
        out.append(
            {
                "id": doc_id,
                "metadata": metas[i] or {},
                "excerpt": (docs[i] or "")[:excerpt_chars],
                "distance": dists[i],
            }
        )
    return out


def _query(coll, query: str, k: int, where_document: dict | None = None) -> list[dict]:
    try:
        res = coll.query(
            query_texts=[query],
            n_results=k,
            where_document=where_document,
        )
    except Exception:
        return []
    return _unpack(res)


def retrieve_vuln_type_context(
    query: str,
    cwe_id: str | None = None,
    k_per_source: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Return a bundle of top-k hits from every vuln-type collection.

    Args:
        query: Free-text description of the finding (e.g. the Semgrep message
            or a snippet summary). Used for semantic search in every collection.
        cwe_id: Optional CWE id (e.g. ``"CWE-89"``). When given, extra CAPEC
            patterns whose embedded text references this CWE are merged into
            the CAPEC results.
        k_per_source: Top-k per collection. Callers should keep this small
            (1-5) so the packed context stays within the agent's budget.

    Returns:
        ``{"cwe": [...], "owasp": [...], "capec": [...], "attack": [...]}``
        where each hit is ``{id, metadata, excerpt, distance}``.
    """
    k = max(1, min(k_per_source, 10))
    chroma = get_chroma()
    cwe_coll = chroma.get_or_create_collection(CWE_COLLECTION)
    owasp_coll = chroma.get_or_create_collection(OWASP_COLLECTION)
    capec_coll = chroma.get_or_create_collection(CAPEC_COLLECTION)
    attack_coll = chroma.get_or_create_collection(ATTACK_COLLECTION)

    bundle: dict[str, list[dict[str, Any]]] = {
        "cwe": _query(cwe_coll, query, k),
        "owasp": _query(owasp_coll, query, k),
        "capec": _query(capec_coll, query, k),
        "attack": _query(attack_coll, query, k),
    }

    if cwe_id:
        # If the CWE is in the store, splice it to the front so callers always
        # see the asked-for entry even if semantic search missed it.
        try:
            direct = cwe_coll.get(ids=[cwe_id])
            if direct.get("ids"):
                direct_hit = {
                    "id": direct["ids"][0],
                    "metadata": (direct.get("metadatas") or [{}])[0] or {},
                    "excerpt": (direct.get("documents") or [""])[0][:800],
                    "distance": 0.0,
                }
                existing = {h["id"] for h in bundle["cwe"]}
                if direct_hit["id"] not in existing:
                    bundle["cwe"].insert(0, direct_hit)
        except Exception:
            pass

        # Pull CAPEC patterns that explicitly cross-reference this CWE id.
        linked = _query(
            capec_coll,
            query,
            k,
            where_document={"$contains": cwe_id},
        )
        existing = {h["id"] for h in bundle["capec"]}
        for hit in linked:
            if hit["id"] not in existing:
                bundle["capec"].append(hit)
                existing.add(hit["id"])

    return bundle
