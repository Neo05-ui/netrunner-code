"""Local brain, via the Ollama HTTP API on 127.0.0.1.

Nothing here ever leaves the machine.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.error

from .base import Reply
from ..log import Timer


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str, model: str, timeout_s: int = 120):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    def chat(self, messages: list[dict], tools: list | None = None) -> Reply:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            # keep_alive stops Ollama unloading 3.4GB between turns, which was
            # costing ~60s of reload on every single message
            "keep_alive": "30m",
            "options": {
                "temperature": 0.45,    # low: small models confabulate at 0.8
                "top_p": 0.9,
                "num_ctx": 2048,        # 4096 is ~2x slower on this CPU
                "num_predict": 140,     # she is terse by design; cap runaway replies
                "num_thread": 4,
            },
        }
        if tools:
            payload["tools"] = tools

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with Timer() as t:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    body = json.loads(r.read().decode("utf-8"))
            msg = body.get("message", {})
            return Reply(
                text=(msg.get("content") or "").strip(),
                model=self.model,
                latency_ms=t.ms,
                tool_calls=msg.get("tool_calls", []) or [],
            )
        except urllib.error.URLError as e:
            return Reply(text="", model=self.model, error=f"ollama unreachable: {e.reason}")
        except Exception as e:
            return Reply(text="", model=self.model, error=f"{type(e).__name__}: {e}")
