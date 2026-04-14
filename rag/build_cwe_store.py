"""Seed the `cwe` SQLite table and the ChromaDB `cwe_entries` collection from MITRE XML.

Usage:
    python -m rag.build_cwe_store --xml path/to/cwec_latest.xml
    python -m rag.build_cwe_store --download      # fetches from cwe.mitre.org

Safe to re-run: both stores upsert by CWE id.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Iterator

import httpx

from db import store as dbstore
from rag.chroma_client import get_chroma, CWE_COLLECTION

CWE_XML_URL = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"
CWE_TOP25_PATH = Path("./data/cwe_top25.json")
NS = {"cwe": "http://cwe.mitre.org/cwe-7"}


def load_top25(path: Path = CWE_TOP25_PATH) -> dict[str, int]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {e["cwe_id"]: int(e["rank"]) for e in payload.get("entries", [])}


def download_xml() -> bytes:
    r = httpx.get(CWE_XML_URL, follow_redirects=True, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        xml_name = next(n for n in z.namelist() if n.endswith(".xml"))
        return z.read(xml_name)


def _text(elem: ET.Element | None) -> str:
    if elem is None:
        return ""
    parts: list[str] = []
    for t in elem.itertext():
        parts.append(t)
    return " ".join(" ".join(parts).split())


def parse_cwe_xml(xml_bytes: bytes) -> Iterator[dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    # Try namespaced and unnamespaced; MITRE has shipped both.
    weaknesses = root.findall(".//cwe:Weaknesses/cwe:Weakness", NS)
    if not weaknesses:
        weaknesses = root.findall(".//Weaknesses/Weakness")

    for w in weaknesses:
        cid = w.get("ID")
        name = w.get("Name", "")
        if not cid:
            continue

        desc_el = (
            w.find("cwe:Description", NS)
            or w.find("Description")
        )
        ext_el = (
            w.find("cwe:Extended_Description", NS)
            or w.find("Extended_Description")
        )
        cons_el = (
            w.find("cwe:Common_Consequences", NS)
            or w.find("Common_Consequences")
        )
        miti_el = (
            w.find("cwe:Potential_Mitigations", NS)
            or w.find("Potential_Mitigations")
        )

        parent_id = None
        rel_root = (
            w.find("cwe:Related_Weaknesses", NS)
            or w.find("Related_Weaknesses")
        )
        if rel_root is not None:
            for rel in rel_root.findall("cwe:Related_Weakness", NS) or rel_root.findall(
                "Related_Weakness"
            ):
                if rel.get("Nature") == "ChildOf":
                    parent_id = f"CWE-{rel.get('CWE_ID')}"
                    break

        yield {
            "id": f"CWE-{cid}",
            "name": name,
            "short_desc": _text(desc_el)[:1000],
            "detail": _text(ext_el)[:4000],
            "consequences": _text(cons_el)[:2000],
            "mitigations": _text(miti_el)[:2000],
            "parent_id": parent_id,
        }


def _embed_text(row: dict[str, str]) -> str:
    return "\n".join(
        filter(
            None,
            [
                f"{row['id']} {row['name']}",
                row.get("short_desc", ""),
                row.get("detail", ""),
            ],
        )
    )


def seed(db_path: str, xml_bytes: bytes) -> tuple[int, int]:
    conn = dbstore.init(db_path)
    rows = list(parse_cwe_xml(xml_bytes))
    sql_n = dbstore.upsert_cwe(conn, rows)

    top25 = load_top25()

    client = get_chroma()
    coll = client.get_or_create_collection(CWE_COLLECTION)
    if rows:
        coll.upsert(
            ids=[r["id"] for r in rows],
            documents=[_embed_text(r) for r in rows],
            metadatas=[
                {
                    "name": r["name"],
                    "parent_id": r["parent_id"] or "",
                    "top25": r["id"] in top25,
                    "top25_rank": top25.get(r["id"], 0),
                }
                for r in rows
            ],
        )
    return sql_n, len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", type=Path, help="Path to cwec_latest.xml")
    ap.add_argument("--download", action="store_true", help="Fetch the XML from mitre.org")
    ap.add_argument("--db", default="./data/audit.db")
    args = ap.parse_args()

    if args.download:
        print(f"downloading {CWE_XML_URL}...")
        xml_bytes = download_xml()
    elif args.xml:
        xml_bytes = args.xml.read_bytes()
    else:
        print("pass --xml PATH or --download", file=sys.stderr)
        return 2

    sql_n, chroma_n = seed(args.db, xml_bytes)
    print(f"seeded {sql_n} CWE rows into SQLite and {chroma_n} into ChromaDB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
