"""Run Semgrep against a cloned repo and normalize output into Candidate dicts.

Semgrep is invoked as a subprocess so we don't depend on its Python API, which
is unstable. In the agents container it's pip-installed; on Windows the host
would use Docker to run it.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CONFIGS = ("p/security-audit", "p/owasp-top-ten")


@dataclass
class Candidate:
    """Normalized Semgrep finding ready for the Ranker."""

    candidate_id: str      # stable hash: "<rule_id>:<path>:<line_start>"
    rule_id: str
    cwe_id: str | None
    path: str              # repo-relative
    line_start: int
    line_end: int
    severity: str          # info | low | medium | high | critical (semgrep uses INFO|WARNING|ERROR)
    message: str
    snippet: str


_CWE_RX = re.compile(r"CWE-(\d+)")


def _extract_cwe(meta: dict) -> str | None:
    raw = meta.get("cwe") or meta.get("cwe2022") or meta.get("cwe-raw")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not raw:
        return None
    m = _CWE_RX.search(str(raw))
    return f"CWE-{m.group(1)}" if m else None


def _map_severity(sev: str) -> str:
    return {
        "INFO": "low",
        "WARNING": "medium",
        "ERROR": "high",
    }.get((sev or "").upper(), "medium")


def is_semgrep_available() -> bool:
    return shutil.which("semgrep") is not None


def run_semgrep(
    clone_root: Path,
    configs: tuple[str, ...] = DEFAULT_CONFIGS,
    timeout_sec: int = 600,
) -> list[Candidate]:
    if not is_semgrep_available():
        raise RuntimeError(
            "semgrep not on PATH. Install in the agents container or run the scanner "
            "step under Docker."
        )
    args = ["semgrep", "scan", "--json", "--quiet", "--metrics=off"]
    for c in configs:
        args += ["--config", c]
    args.append(str(clone_root))
    log.info("running: %s", " ".join(args))
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout_sec
    )
    if proc.returncode not in (0, 1):  # 1 = findings present, still ok
        raise RuntimeError(f"semgrep failed ({proc.returncode}): {proc.stderr[:500]}")
    data = json.loads(proc.stdout or "{}")
    return normalize(data, clone_root)


def normalize(semgrep_json: dict, clone_root: Path) -> list[Candidate]:
    out: list[Candidate] = []
    for r in semgrep_json.get("results", []):
        rule_id = r.get("check_id") or "unknown"
        path = Path(r.get("path") or "").resolve()
        try:
            rel = path.relative_to(clone_root.resolve()).as_posix()
        except ValueError:
            rel = str(path)
        start = int((r.get("start") or {}).get("line", 1))
        end = int((r.get("end") or {}).get("line", start))
        extra = r.get("extra") or {}
        meta = extra.get("metadata") or {}
        cwe = _extract_cwe(meta)
        snippet = (extra.get("lines") or "").strip()[:800]
        cand_id = f"{rule_id}:{rel}:{start}"
        out.append(
            Candidate(
                candidate_id=cand_id,
                rule_id=rule_id,
                cwe_id=cwe,
                path=rel,
                line_start=start,
                line_end=end,
                severity=_map_severity(extra.get("severity", "")),
                message=(extra.get("message") or "").strip()[:800],
                snippet=snippet,
            )
        )
    return out


def to_dicts(candidates: list[Candidate]) -> list[dict]:
    return [asdict(c) for c in candidates]
