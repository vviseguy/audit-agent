"""Seed the ChromaDB `owasp_top10` collection from a vendored JSON file.

Usage:
    python -m rag.build_owasp_store
    python -m rag.build_owasp_store --seed path/to/owasp_top10.json

The vendored seed at ``data/owasp_top10.json`` is the 2021 edition with
CWE cross-references. Rebuild annually when OWASP publishes a new list.

Safe to re-run: upserts by OWASP category id (e.g. ``A03:2021``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rag.chroma_client import OWASP_COLLECTION, get_chroma

DEFAULT_SEED = Path("./data/owasp_top10.json")


def _embed_text(entry: dict) -> str:
    return "\n".join(
        filter(
            None,
            [
                f"{entry['id']} {entry['name']}",
                entry.get("description", ""),
                entry.get("example_scenarios", ""),
            ],
        )
    )


def seed(seed_path: Path) -> int:
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    categories = payload.get("categories", [])
    if not categories:
        return 0

    coll = get_chroma().get_or_create_collection(OWASP_COLLECTION)
    coll.upsert(
        ids=[c["id"] for c in categories],
        documents=[_embed_text(c) for c in categories],
        metadatas=[
            {
                "name": c["name"],
                "rank": int(c["rank"]),
                "version": payload.get("version", ""),
                "related_cwes": ",".join(c.get("related_cwes", [])),
            }
            for c in categories
        ],
    )
    return len(categories)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    args = ap.parse_args()

    if not args.seed.exists():
        print(f"seed file not found: {args.seed}", file=sys.stderr)
        return 2

    n = seed(args.seed)
    print(f"seeded {n} OWASP Top 10 categories into ChromaDB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
