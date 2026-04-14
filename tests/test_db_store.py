"""SQLite store is the source of truth for every structured entity, so a
few basic round-trip checks catch schema drift and FK regressions fast."""

from __future__ import annotations

import json

from db import store as dbstore


def test_schema_initializes_with_core_tables(db):
    names = {
        r["name"]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for required in [
        "project",
        "repo",
        "vulnerability",
        "annotation",
        "journal_entry",
        "draft_issue",
        "run",
        "session",
        "cwe",
        "token_ledger",
        "github_token",
    ]:
        assert required in names, f"missing table: {required}"


def test_append_journal_round_trip(db):
    jid = dbstore.append_journal(
        db,
        vulnerability_id=None,
        run_id=None,
        agent="system",
        action="note",
        payload={"hello": "world"},
    )
    row = db.execute(
        "SELECT * FROM journal_entry WHERE id=?", (jid,)
    ).fetchone()
    assert row is not None
    assert row["agent"] == "system"
    assert row["action"] == "note"
    assert json.loads(row["payload_json"]) == {"hello": "world"}


def test_token_ledger_accumulates_per_day(db):
    dbstore.add_tokens_today(db, tokens_in=1000, tokens_out=500, cost_usd=0.01)
    dbstore.add_tokens_today(db, tokens_in=200, tokens_out=100, cost_usd=0.002)
    total = dbstore.tokens_used_today(db)
    assert total == 1000 + 500 + 200 + 100


def test_cwe_upsert_is_idempotent(db):
    row = {
        "id": "CWE-89",
        "name": "SQL Injection",
        "short_desc": "nope",
        "detail": "",
        "consequences": "",
        "mitigations": "",
        "parent_id": None,
    }
    dbstore.upsert_cwe(db, [row])
    dbstore.upsert_cwe(db, [{**row, "short_desc": "updated"}])
    got = dbstore.get_cwe(db, "CWE-89")
    assert got is not None
    assert got["short_desc"] == "updated"
    count = db.execute("SELECT COUNT(*) AS c FROM cwe").fetchone()["c"]
    assert count == 1
