"""Seed the ChromaDB `attack_techniques` collection from MITRE ATT&CK STIX.

Usage:
    python -m rag.build_attack_store --json path/to/enterprise-attack.json
    python -m rag.build_attack_store --download    # fetches from github.com/mitre/cti

ATT&CK is MITRE's catalog of adversary techniques. It's less directly aimed at
source-code audits than CWE/CAPEC, but it gives the Delver a vocabulary for
describing post-exploitation behavior in draft issues (e.g. a deserialization
finding maps to T1059 Command and Scripting Interpreter).

Safe to re-run: upserts by technique id (e.g. ``T1190``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterator

import httpx

from rag.chroma_client import ATTACK_COLLECTION, get_chroma

ATTACK_URL = (
    "https://raw.githubusercontent.com/mitre/cti/master/"
    "enterprise-attack/enterprise-attack.json"
)
BATCH = 200


def download_bundle() -> dict:
    r = httpx.get(ATTACK_URL, follow_redirects=True, timeout=180)
    r.raise_for_status()
    return r.json()


def _technique_id(obj: dict) -> str | None:
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id"):
            return ref["external_id"]
    return None


def _related_capec(obj: dict) -> list[str]:
    out: list[str] = []
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "capec" and ref.get("external_id"):
            out.append(ref["external_id"])
    return out


def _tactics(obj: dict) -> list[str]:
    return [
        p.get("phase_name", "")
        for p in obj.get("kill_chain_phases", [])
        if p.get("kill_chain_name") == "mitre-attack"
    ]


def parse_attack_bundle(bundle: dict) -> Iterator[dict]:
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        tid = _technique_id(obj)
        if not tid:
            continue

        description = (obj.get("description") or "").strip()
        detection = (obj.get("x_mitre_detection") or "").strip()
        platforms = obj.get("x_mitre_platforms") or []
        tactics = _tactics(obj)
        capec = _related_capec(obj)

        yield {
            "id": tid,
            "name": obj.get("name", ""),
            "is_subtechnique": bool(obj.get("x_mitre_is_subtechnique")),
            "platforms": platforms,
            "tactics": tactics,
            "description": description[:3000],
            "detection": detection[:1500],
            "related_capec": capec,
        }


def _embed_text(row: dict) -> str:
    return "\n".join(
        filter(
            None,
            [
                f"{row['id']} {row['name']}",
                ("Tactics: " + ", ".join(row["tactics"])) if row["tactics"] else "",
                row.get("description", ""),
                ("Detection: " + row["detection"]) if row.get("detection") else "",
            ],
        )
    )


def seed(bundle: dict) -> int:
    rows = list(parse_attack_bundle(bundle))
    if not rows:
        return 0
    coll = get_chroma().get_or_create_collection(ATTACK_COLLECTION)
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        coll.upsert(
            ids=[r["id"] for r in chunk],
            documents=[_embed_text(r) for r in chunk],
            metadatas=[
                {
                    "name": r["name"],
                    "is_subtechnique": r["is_subtechnique"],
                    "platforms": ",".join(r["platforms"]),
                    "tactics": ",".join(r["tactics"]),
                    "related_capec": ",".join(r["related_capec"]),
                }
                for r in chunk
            ],
        )
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, help="Path to enterprise-attack.json")
    ap.add_argument("--download", action="store_true", help="Fetch from github.com/mitre/cti")
    args = ap.parse_args()

    if args.download:
        print(f"downloading {ATTACK_URL}...")
        bundle = download_bundle()
    elif args.json:
        bundle = json.loads(args.json.read_text(encoding="utf-8"))
    else:
        print("pass --json PATH or --download", file=sys.stderr)
        return 2

    n = seed(bundle)
    print(f"seeded {n} ATT&CK techniques into ChromaDB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
