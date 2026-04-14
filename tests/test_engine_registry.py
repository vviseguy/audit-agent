"""The @tool registry is what makes the engine agent-independent — adding a
specialist agent means dropping a YAML that references tools by name."""

from __future__ import annotations

import pytest

from engine import registry


@pytest.fixture
def fresh_registry():
    snapshot = dict(registry._REGISTRY)
    registry.clear()
    try:
        yield
    finally:
        registry.clear()
        registry._REGISTRY.update(snapshot)


def test_decorator_registers_and_resolves_by_name(fresh_registry):
    @registry.tool(
        name="echo",
        description="echo back",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
    )
    def echo(x: str) -> str:
        return x

    spec = registry.get("echo")
    assert spec.name == "echo"
    assert spec.func("hi") == "hi"


def test_to_anthropic_strips_func(fresh_registry):
    @registry.tool(
        name="t",
        description="d",
        input_schema={"type": "object"},
    )
    def _t() -> None:
        return None

    payload = registry.get("t").to_anthropic()
    assert set(payload.keys()) == {"name", "description", "input_schema"}


def test_resolve_many_preserves_order(fresh_registry):
    @registry.tool(name="a", description="", input_schema={"type": "object"})
    def _a() -> None:
        return None

    @registry.tool(name="b", description="", input_schema={"type": "object"})
    def _b() -> None:
        return None

    specs = registry.resolve(["b", "a"])
    assert [s.name for s in specs] == ["b", "a"]


def test_missing_tool_raises(fresh_registry):
    with pytest.raises(KeyError):
        registry.get("nope")


def test_duplicate_registration_blocked(fresh_registry):
    @registry.tool(name="dup", description="", input_schema={"type": "object"})
    def _first() -> None:
        return None

    with pytest.raises(ValueError):
        @registry.tool(name="dup", description="", input_schema={"type": "object"})
        def _second() -> None:
            return None
