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
                # 0.45 was chosen against llama3.1 to curb confabulation.
                # Measured on llama3.2:3b, 3 samples each: both 0.45 and 0.25
                # scored 0/3 for robot register, cruelty and lecturing, but
                # 0.25 was consistently warmer and more concrete ("Built a
                # whole world for her, and it still wasn't enough"). The rare
                # bad draws - a three-paragraph lecture, "I'm just a tool" -
                # came from the tail of the 0.45 distribution, not from the
                # persona. Narrowing the distribution is the real fix; four
                # rounds of persona edits before this were chasing noise.
                "temperature": 0.3,
                "top_p": 0.9,
                # 2048 was sized for llama3.1:8b. On the 3B model a longer
                # window is affordable, and a real conversation overflowed
                # the old one - which silently drops the start of the thread.
                "num_ctx": 4096,
                # 140 cut her off mid-sentence ("...and it's clear that it
                # wasn't"). She is terse by choice, not by truncation.
                "num_predict": 320,
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
