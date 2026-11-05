"""Structured turn logging. One JSON object per line, easy to grep and replay."""
from __future__ import annotations
import json, time
from datetime import datetime
from pathlib import Path


class TurnLog:
    def __init__(self, root: Path, dirname: str = "logs"):
        self.dir = Path(root) / dirname
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{datetime.now():%Y-%m-%d}.jsonl"

    def write(self, **fields) -> None:
        fields["ts"] = datetime.now().isoformat(timespec="seconds")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(fields, ensure_ascii=False) + "\n")


class Timer:
    """with Timer() as t: ...   ->  t.ms"""
    def __enter__(self):
        self._t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = int((time.perf_counter() - self._t) * 1000)
        return False
