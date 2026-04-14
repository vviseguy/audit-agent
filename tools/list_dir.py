from __future__ import annotations

from tools.base import tool
from tools.sandbox import resolve

IGNORED = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
MAX_ENTRIES = 500


@tool(
    name="list_dir",
    description="List the contents of a directory inside the sandboxed clone, skipping vendored dirs.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repo-relative directory path. Use '' for the root."},
            "recursive": {"type": "boolean"},
        },
        "required": ["path"],
    },
)
def list_dir(path: str, recursive: bool = False) -> str:
    p = resolve(path) if path else resolve(".")
    if not p.is_dir():
        return f"[not a directory: {path}]"
    lines: list[str] = []
    if recursive:
        for entry in sorted(p.rglob("*")):
            if any(part in IGNORED for part in entry.relative_to(p).parts):
                continue
            rel = entry.relative_to(resolve("."))
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{rel.as_posix()}{suffix}")
            if len(lines) >= MAX_ENTRIES:
                lines.append(f"[truncated at {MAX_ENTRIES}]")
                break
    else:
        for entry in sorted(p.iterdir()):
            if entry.name in IGNORED:
                continue
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
    return "\n".join(lines)
