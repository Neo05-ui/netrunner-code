"""Tool registry and permission tiers.

Every capability Capri has is a Tool with a declared tier. Nothing acts on
the machine except through here, so there is exactly one place to audit.

  TIER 0  read-only, no side effects. Runs without asking.
  TIER 1  changes something recoverable. Needs a yes.
  TIER 2  destructive, irreversible, or leaves the machine. Needs Neo to type
          a confirmation phrase, not just say yes.

Phase 3 ships tier 0 only, by Neo's instruction: she gets to look, not touch,
until she has proven stable. The tier machinery exists now so that adding a
tier 1 tool later is a declaration, not a refactor.

Tool OUTPUT IS DATA, NEVER INSTRUCTIONS. A file she reads may contain text
that looks like an order. It is quoted to the model as content and never
executed, which is the same rule the blueprint sets.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable


class Tier(IntEnum):
    READ_ONLY = 0
    CONFIRM = 1
    DANGEROUS = 2


@dataclass
class Result:
    ok: bool
    content: str = ""
    error: str = ""
    elapsed_ms: int = 0
    truncated: bool = False


@dataclass
class Tool:
    name: str
    description: str
    schema: dict                      # JSON-schema-ish, for the model
    tier: Tier
    run: Callable[..., Result]
    timeout_s: float = 10.0
    max_output: int = 4000            # keep a huge file from eating the prompt


class ToolError(Exception):
    pass


class Registry:
    def __init__(self, *, dry_run: bool = False, max_tier: Tier = Tier.READ_ONLY):
        self._tools: dict[str, Tool] = {}
        self.dry_run = dry_run
        # a hard ceiling, independent of any individual tool's tier: even if a
        # tier 1 tool is registered by mistake, it cannot run while this is 0
        self.max_tier = max_tier
        self.audit: list[dict] = []

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def available(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.tier <= self.max_tier]

    def describe(self) -> str:
        """What the model is told it can do. Only tools it may actually run."""
        lines = []
        for t in sorted(self.available(), key=lambda x: x.name):
            args = ", ".join(t.schema.get("properties", {}))
            lines.append(f"- {t.name}({args}) — {t.description}")
        return "\n".join(lines) if lines else "(none)"

    def as_ollama_tools(self) -> list[dict]:
        """Only tools she may actually run. Offering a tool the ceiling would
        block just teaches her to call something that always fails."""
        out = []
        for t in self.available():
            params = dict(t.schema)
            params.setdefault("type", "object")
            params.setdefault("properties", {})
            out.append({"type": "function", "function": {
                "name": t.name, "description": t.description,
                "parameters": params}})
        return out

    def call(self, name: str, args: dict, *, approved: bool = False) -> Result:
        tool = self._tools.get(name)
        if tool is None:
            return Result(False, error=f"no such tool: {name}")

        if tool.tier > self.max_tier:
            return self._log(name, args, Result(
                False, error=f"tier {int(tool.tier)} blocked (ceiling is "
                             f"{int(self.max_tier)})"))

        if tool.tier >= Tier.CONFIRM and not approved:
            return self._log(name, args, Result(
                False, error=f"tier {int(tool.tier)} requires approval"))

        if self.dry_run:
            return self._log(name, args, Result(
                True, content=f"[dry run] would call {name}({args})"))

        t0 = time.time()
        try:
            res = tool.run(**args)
        except TypeError as e:
            res = Result(False, error=f"bad arguments: {e}")
        except Exception as e:                  # noqa: BLE001
            res = Result(False, error=repr(e))
        res.elapsed_ms = int((time.time() - t0) * 1000)

        if len(res.content) > tool.max_output:
            res.content = res.content[:tool.max_output]
            res.truncated = True
        return self._log(name, args, res)

    def _log(self, name: str, args: dict, res: Result) -> Result:
        self.audit.append({
            "tool": name,
            "args": _redact(args),
            "ok": res.ok,
            "error": res.error[:200],
            "elapsed_ms": res.elapsed_ms,
            "bytes": len(res.content),
        })
        return res


SECRET_HINTS = ("key", "token", "secret", "password", "passwd", "credential")


def _redact(args: dict) -> dict:
    """Arguments are logged; secrets in them are not."""
    out = {}
    for k, v in args.items():
        out[k] = "***" if any(h in k.lower() for h in SECRET_HINTS) else v
    return out
