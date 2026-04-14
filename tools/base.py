"""Tool authoring contract.

Each tool file in this folder exports one function decorated with @tool:

    from tools.base import tool

    @tool(
        name="read_file",
        description="Read a file from the sandboxed clone root.",
        input_schema={"type": "object", "properties": {...}, "required": [...]},
    )
    def read_file(...): ...

The decorator registers the callable in engine.registry so an agent YAML can
reference it by name.
"""

from engine.registry import tool, ToolSpec, get, resolve, all_tools  # noqa: F401
