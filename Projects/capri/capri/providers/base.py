"""One interface every brain implements.

Adding a provider later (Gemini, whatever) means adding one class that
satisfies this, and nothing else in the codebase changes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Reply:
    text: str
    model: str
    latency_ms: int = 0
    tool_calls: list = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Provider(Protocol):
    name: str

    def chat(self, messages: list[dict], tools: list | None = None) -> Reply:
        ...

    def available(self) -> bool:
        ...
