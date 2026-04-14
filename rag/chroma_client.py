"""Thin ChromaDB client wrapper.

Collections:
  - cwe_entries        : one doc per CWE, for semantic CWE lookup
  - project_memory     : one doc per journal/vuln summary, per project, for similarity search
  - owasp_top10        : one doc per OWASP Top 10 category (developer-facing vuln types)
  - capec_patterns     : one doc per CAPEC attack pattern (exploit-flow knowledge)
  - attack_techniques  : one doc per MITRE ATT&CK technique/sub-technique
"""

from __future__ import annotations

import os
from functools import lru_cache

import chromadb
from chromadb.config import Settings

CWE_COLLECTION = "cwe_entries"
PROJECT_MEMORY_COLLECTION = "project_memory"
OWASP_COLLECTION = "owasp_top10"
CAPEC_COLLECTION = "capec_patterns"
ATTACK_COLLECTION = "attack_techniques"


@lru_cache(maxsize=1)
def get_chroma() -> chromadb.api.ClientAPI:
    path = os.environ.get("CHROMA_PATH", "./data/chroma")
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))
