"""Thin ChromaDB client wrapper.

Two collections:
  - cwe_entries     : one doc per CWE, for semantic CWE lookup
  - project_memory  : one doc per journal/vuln summary, per project, for similarity search
"""

from __future__ import annotations

import os
from functools import lru_cache

import chromadb
from chromadb.config import Settings

CWE_COLLECTION = "cwe_entries"
PROJECT_MEMORY_COLLECTION = "project_memory"


@lru_cache(maxsize=1)
def get_chroma() -> chromadb.api.ClientAPI:
    path = os.environ.get("CHROMA_PATH", "./data/chroma")
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))
