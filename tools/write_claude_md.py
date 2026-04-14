from __future__ import annotations

import json

from tools.base import tool
from tools.sandbox import resolve


@tool(
    name="write_claude_md",
    description=(
        "Understander-only: write a CLAUDE.md note into a directory of the cloned repo. "
        "Call once per directory you've understood. The file stays inside the sandbox; "
        "it is never pushed to GitHub."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dir_path": {"type": "string", "description": "Repo-relative directory."},
            "summary": {"type": "string", "description": "1-3 sentence purpose."},
            "entry_point": {"type": "boolean"},
            "trust_boundary": {"type": "boolean"},
            "dataflows": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Notable dataflows, e.g. 'user input -> shell'.",
            },
            "dependencies": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["dir_path", "summary", "entry_point", "trust_boundary"],
    },
)
def write_claude_md(
    dir_path: str,
    summary: str,
    entry_point: bool,
    trust_boundary: bool,
    dataflows: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> str:
    target_dir = resolve(dir_path) if dir_path else resolve(".")
    if not target_dir.is_dir():
        return f"[not a directory: {dir_path}]"

    md_path = target_dir / "CLAUDE.md"
    body = _render(
        summary=summary,
        entry_point=entry_point,
        trust_boundary=trust_boundary,
        dataflows=dataflows or [],
        dependencies=dependencies or [],
    )
    md_path.write_text(body, encoding="utf-8")

    return json.dumps(
        {
            "wrote": str(md_path.name),
            "dir": dir_path,
            "trust_boundary": trust_boundary,
            "entry_point": entry_point,
            "bytes": len(body.encode("utf-8")),
        }
    )


def _render(
    *,
    summary: str,
    entry_point: bool,
    trust_boundary: bool,
    dataflows: list[str],
    dependencies: list[str],
) -> str:
    lines = [
        "# Module notes",
        "",
        "_Written by the cyber-audit Understander agent. Do not edit; will be overwritten on re-annotation._",
        "",
        "## Purpose",
        "",
        summary,
        "",
        f"- **Entry point:** {'yes' if entry_point else 'no'}",
        f"- **Trust boundary:** {'yes' if trust_boundary else 'no'}",
        "",
    ]
    if dataflows:
        lines += ["## Dataflows", ""]
        lines += [f"- {d}" for d in dataflows]
        lines.append("")
    if dependencies:
        lines += ["## Dependencies", ""]
        lines += [f"- {d}" for d in dependencies]
        lines.append("")
    return "\n".join(lines)
