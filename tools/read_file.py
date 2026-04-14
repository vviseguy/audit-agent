from __future__ import annotations

from tools.base import tool
from tools.sandbox import resolve

MAX_BYTES = 200_000


@tool(
    name="read_file",
    description=(
        "Read a file from the cloned target repo. Paths are repo-relative and sandboxed "
        "to the clone root. Supports an optional line range to avoid pulling large files."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repo-relative path."},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
        },
        "required": ["path"],
    },
)
def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
    p = resolve(path)
    if not p.is_file():
        return f"[not a file: {path}]"
    data = p.read_bytes()[:MAX_BYTES]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    lo = max(start_line - 1, 0)
    hi = end_line if end_line is not None else len(lines)
    sliced = lines[lo:hi]
    numbered = [f"{i + 1 + lo:>6}: {line}" for i, line in enumerate(sliced)]
    return "\n".join(numbered)
