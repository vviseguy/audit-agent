"""Seed the ChromaDB `capec_patterns` collection from MITRE CAPEC XML.

Usage:
    python -m rag.build_capec_store --xml path/to/capec_latest.xml
    python -m rag.build_capec_store --download     # fetches from capec.mitre.org

CAPEC is MITRE's catalog of *attack patterns* (how attackers exploit a weakness
class). Each pattern links to related CWEs, which is how the Delver joins
exploit-flow knowledge back to a vulnerability's CWE id.

Safe to re-run: upserts by CAPEC id (e.g. ``CAPEC-66``).
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator

import httpx

from rag.chroma_client import CAPEC_COLLECTION, get_chroma

CAPEC_XML_URL = "https://capec.mitre.org/data/xml/capec_latest.xml"
NS = {"capec": "http://capec.mitre.org/capec-3"}
BATCH = 200


def download_xml() -> bytes:
    r = httpx.get(CAPEC_XML_URL, follow_redirects=True, timeout=120)
    r.raise_for_status()
    return r.content


def _text(elem: ET.Element | None) -> str:
    if elem is None:
        return ""
    return " ".join(" ".join(elem.itertext()).split())


def _find(parent: ET.Element, local: str) -> ET.Element | None:
    # Try namespaced first, fall back to unnamespaced
    return parent.find(f"capec:{local}", NS) or parent.find(local)


def _findall(parent: ET.Element, local: str) -> list[ET.Element]:
    hits = parent.findall(f"capec:{local}", NS)
    if not hits:
        hits = parent.findall(local)
    return hits


def parse_capec_xml(xml_bytes: bytes) -> Iterator[dict]:
    root = ET.fromstring(xml_bytes)
    patterns_root = (
        root.find(".//capec:Attack_Patterns", NS)
        or root.find(".//Attack_Patterns")
    )
    if patterns_root is None:
        return
    attack_patterns = (
        patterns_root.findall("capec:Attack_Pattern", NS)
        or patterns_root.findall("Attack_Pattern")
    )

    for ap in attack_patterns:
        pid = ap.get("ID")
        if not pid:
            continue
        status = (ap.get("Status") or "").lower()
        if status in {"deprecated", "obsolete"}:
            continue

        desc = _text(_find(ap, "Description"))
        likelihood = _text(_find(ap, "Likelihood_Of_Attack"))
        severity = _text(_find(ap, "Typical_Severity"))

        prereq_root = _find(ap, "Prerequisites")
        prerequisites = ""
        if prereq_root is not None:
            prereq_items = [
                _text(p) for p in _findall(prereq_root, "Prerequisite")
            ]
            prerequisites = " | ".join(p for p in prereq_items if p)

        flow_root = _find(ap, "Execution_Flow")
        execution_flow = ""
        if flow_root is not None:
            steps: list[str] = []
            for step in _findall(flow_root, "Attack_Step"):
                title = _text(_find(step, "Title"))
                stext = _text(_find(step, "Description"))
                if title or stext:
                    steps.append(f"- {title}: {stext}".strip())
            execution_flow = "\n".join(steps)

        related_cwes: list[str] = []
        rw_root = _find(ap, "Related_Weaknesses")
        if rw_root is not None:
            for rw in _findall(rw_root, "Related_Weakness"):
                cwe_id = rw.get("CWE_ID")
                if cwe_id:
                    related_cwes.append(f"CWE-{cwe_id}")

        related_attack: list[str] = []
        rap_root = _find(ap, "Related_Attack_Patterns")
        if rap_root is not None:
            for rap in _findall(rap_root, "Related_Attack_Pattern"):
                rid = rap.get("CAPEC_ID")
                if rid:
                    related_attack.append(f"CAPEC-{rid}")

        yield {
            "id": f"CAPEC-{pid}",
            "name": ap.get("Name", ""),
            "abstraction": ap.get("Abstraction", ""),
            "likelihood": likelihood,
            "severity": severity,
            "description": desc[:2000],
            "prerequisites": prerequisites[:1500],
            "execution_flow": execution_flow[:3000],
            "related_cwes": related_cwes,
            "related_attack": related_attack,
        }


def _embed_text(row: dict) -> str:
    return "\n".join(
        filter(
            None,
            [
                f"{row['id']} {row['name']}",
                row.get("description", ""),
                ("Prerequisites: " + row["prerequisites"]) if row.get("prerequisites") else "",
                ("Execution flow:\n" + row["execution_flow"]) if row.get("execution_flow") else "",
            ],
        )
    )


def seed(xml_bytes: bytes) -> int:
    rows = list(parse_capec_xml(xml_bytes))
    if not rows:
        return 0
    coll = get_chroma().get_or_create_collection(CAPEC_COLLECTION)
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        coll.upsert(
            ids=[r["id"] for r in chunk],
            documents=[_embed_text(r) for r in chunk],
            metadatas=[
                {
                    "name": r["name"],
                    "abstraction": r["abstraction"],
                    "likelihood": r["likelihood"],
                    "severity": r["severity"],
                    "related_cwes": ",".join(r["related_cwes"]),
                    "related_attack": ",".join(r["related_attack"]),
                }
                for r in chunk
            ],
        )
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", type=Path, help="Path to capec_latest.xml")
    ap.add_argument("--download", action="store_true", help="Fetch from capec.mitre.org")
    args = ap.parse_args()

    if args.download:
        print(f"downloading {CAPEC_XML_URL}...")
        xml_bytes = download_xml()
    elif args.xml:
        xml_bytes = args.xml.read_bytes()
    else:
        print("pass --xml PATH or --download", file=sys.stderr)
        return 2

    n = seed(xml_bytes)
    print(f"seeded {n} CAPEC attack patterns into ChromaDB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
