from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RateLimit:
    requests_per_minute: int = 60
    max_calls_per_job: int = 100


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str                         # understander | ranker | delver
    model: str
    max_tokens: int
    temperature: float
    rate_limit: RateLimit
    per_call_token_cap: int
    prompt_cache: tuple[str, ...]     # which blocks to cache: system, cwe_context, etc.
    system_prompt_file: str
    tools: tuple[str, ...]
    output_schema: str | None
    batch_size: int | None
    extra: dict[str, Any] = field(default_factory=dict)

    def load_system_prompt(self, base: Path) -> str:
        path = base / self.system_prompt_file
        return path.read_text(encoding="utf-8")


def load_agent(path: str | Path) -> AgentSpec:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rl = raw.get("rate_limit", {}) or {}
    budget = raw.get("budget", {}) or {}
    return AgentSpec(
        name=raw["name"],
        role=raw["role"],
        model=raw["model"],
        max_tokens=int(raw.get("max_tokens", 2048)),
        temperature=float(raw.get("temperature", 0)),
        rate_limit=RateLimit(
            requests_per_minute=int(rl.get("requests_per_minute", 60)),
            max_calls_per_job=int(rl.get("max_calls_per_job", 100)),
        ),
        per_call_token_cap=int(budget.get("per_call_token_cap", 8000)),
        prompt_cache=tuple(raw.get("prompt_cache", [])),
        system_prompt_file=raw["system_prompt_file"],
        tools=tuple(raw.get("tools", [])),
        output_schema=raw.get("output_schema"),
        batch_size=raw.get("batch_size"),
        extra={
            k: v
            for k, v in raw.items()
            if k
            not in {
                "name",
                "role",
                "model",
                "max_tokens",
                "temperature",
                "rate_limit",
                "budget",
                "prompt_cache",
                "system_prompt_file",
                "tools",
                "output_schema",
                "batch_size",
            }
        },
    )


def load_all_agents(agents_dir: str | Path) -> dict[str, AgentSpec]:
    base = Path(agents_dir)
    specs: dict[str, AgentSpec] = {}
    for p in sorted(base.glob("*.yaml")):
        spec = load_agent(p)
        specs[spec.name] = spec
    return specs
