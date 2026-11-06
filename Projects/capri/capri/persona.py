"""Persona loading with hot-reload.

persona.md is re-read whenever it changes on disk, so editing her character
takes effect on the next turn with no restart.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import yaml


class Persona:
    def __init__(self, root: Path, name: str):
        self.dir = Path(root) / "personas" / name
        self.name = name
        self._mtime = 0.0
        self._text = ""
        self.voice = {}
        self.emotions = {}
        self._load_sidecars()

    @property
    def prompt_path(self) -> Path:
        return self.dir / "persona.md"

    def _load_sidecars(self) -> None:
        for attr, fn in (("voice", "voice.yaml"), ("emotions", "emotions.yaml")):
            p = self.dir / fn
            if p.exists():
                setattr(self, attr, yaml.safe_load(p.read_text(encoding="utf-8")) or {})

    def _maybe_reload(self) -> None:
        m = self.prompt_path.stat().st_mtime
        if m != self._mtime:
            self._text = self.prompt_path.read_text(encoding="utf-8")
            self._mtime = m
            self._load_sidecars()

    def system_prompt(self, *, facts: str, user_name: str) -> str:
        self._maybe_reload()
        return (
            self._text
            .replace("{{facts}}", facts or "(nothing recorded yet)")
            .replace("{{user_name}}", user_name)
            # The clock does NOT belong in the system prompt. It changes every
            # minute, which moves the cached prefix and forces Ollama to
            # re-evaluate the whole thing: measured 0.4s on a cache hit
            # against 36.1s on a miss, for the identical question. The time
            # is injected at the TAIL of the message list instead, where it
            # costs nothing. See Capri._now_block().
            .replace("{{now}}", "")
        )
