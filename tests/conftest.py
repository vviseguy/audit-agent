"""Shared fixtures for the pytest suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from db import store as dbstore


@pytest.fixture
def db(tmp_path: Path):
    """A freshly-initialized SQLite database in a temp dir."""
    conn = dbstore.init(tmp_path / "test.db")
    try:
        yield conn
    finally:
        conn.close()
