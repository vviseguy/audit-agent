"""Upsert and query the project_memory ChromaDB collection.

Stores one doc per journal entry and per vulnerability summary, scoped by
project_id, so the Delver can ask "have we seen something like this before
in THIS project?" without leaking across projects.
"""

from __future__ import annotations

from typing import Any

from rag.chroma_client import PROJECT_MEMORY_COLLECTION, get_chroma


def _coll():
    return get_chroma().get_or_create_collection(PROJECT_MEMORY_COLLECTION)


def _doc_id(kind: str, pk: int) -> str:
    return f"{kind}:{pk}"


def upsert_vulnerability(
    *,
    project_id: int,
    vulnerability_id: int,
    cwe_id: str | None,
    path: str,
    title: str,
    short_desc: str,
) -> None:
    text = f"{title}\n{short_desc}\n{path}"
    _coll().upsert(
        ids=[_doc_id("vuln", vulnerability_id)],
        documents=[text],
        metadatas=[
            {
                "project_id": int(project_id),
                "vulnerability_id": int(vulnerability_id),
                "cwe_id": cwe_id or "",
                "path": path,
                "kind": "vulnerability",
            }
        ],
    )


def upsert_journal_entry(
    *,
    project_id: int,
    vulnerability_id: int | None,
    journal_id: int,
    cwe_id: str | None,
    path: str,
    text: str,
) -> None:
    _coll().upsert(
        ids=[_doc_id("journal", journal_id)],
        documents=[text],
        metadatas=[
            {
                "project_id": int(project_id),
                "vulnerability_id": int(vulnerability_id) if vulnerability_id else -1,
                "journal_id": int(journal_id),
                "cwe_id": cwe_id or "",
                "path": path,
                "kind": "journal",
            }
        ],
    )


def query_similar(
    *,
    project_id: int,
    query_text: str,
    k: int = 5,
    cwe_id: str | None = None,
) -> list[dict[str, Any]]:
    where: dict[str, Any] = {"project_id": int(project_id)}
    if cwe_id:
        where = {"$and": [where, {"cwe_id": cwe_id}]}
    res = _coll().query(query_texts=[query_text], n_results=k, where=where)
    out: list[dict[str, Any]] = []
    if not res.get("ids") or not res["ids"][0]:
        return out
    for i, doc_id in enumerate(res["ids"][0]):
        out.append(
            {
                "id": doc_id,
                "document": res["documents"][0][i],
                "metadata": res["metadatas"][0][i],
                "distance": res["distances"][0][i] if res.get("distances") else None,
            }
        )
    return out
