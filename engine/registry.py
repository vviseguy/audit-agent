from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    func: Callable[..., Any]

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


_REGISTRY: dict[str, ToolSpec] = {}


def tool(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        if name in _REGISTRY:
            raise ValueError(f"tool {name!r} already registered")
        _REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            input_schema=input_schema,
            func=func,
        )
        return func

    return decorate


def get(name: str) -> ToolSpec:
    if name not in _REGISTRY:
        raise KeyError(
            f"tool {name!r} is not registered. Registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def resolve(names: Iterable[str]) -> list[ToolSpec]:
    return [get(n) for n in names]


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def clear() -> None:
    _REGISTRY.clear()
