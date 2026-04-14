from __future__ import annotations

import re

from tools.base import tool
from tools.sandbox import get_root, resolve

MAX_MATCHES = 200
IGNORED = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}


@tool(
    name="grep",
    description="Regex search inside the sandboxed clone. Returns file:line matches.",
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "Repo-relative subdir to scope the search. Optional."},
            "glob": {"type": "string", "description": "Optional filename glob, e.g. '*.py'."},
        },
        "required": ["pattern"],
    },
)
def grep(pattern: str, path: str = "", glob: str = "") -> str:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"[invalid regex: {exc}]"
    base = resolve(path) if path else get_root()
    if not base.is_dir():
        return f"[not a directory: {path}]"
    results: list[str] = []
    iterator = base.rglob(glob) if glob else base.rglob("*")
    for entry in iterator:
        if not entry.is_file():
            continue
        if any(part in IGNORED for part in entry.relative_to(base).parts):
            continue
        try:
            with entry.open("r", encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh, start=1):
                    if rx.search(line):
                        rel = entry.relative_to(get_root()).as_posix()
                        results.append(f"{rel}:{i}: {line.rstrip()}")
                        if len(results) >= MAX_MATCHES:
                            results.append(f"[truncated at {MAX_MATCHES}]")
                            return "\n".join(results)
        except OSError:
            continue
    return "\n".join(results) if results else "[no matches]"
