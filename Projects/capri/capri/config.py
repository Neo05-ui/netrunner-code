"""Load config.yaml once and expose it as a plain dict."""
from __future__ import annotations
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load(path: str | Path | None = None) -> dict:
    """`_root` is the directory holding the config that was loaded, NOT the
    package directory. Every relative path in the config resolves against it,
    so an instance pointed at another config keeps its memory, logs and data
    to itself. Hardcoding the package root here meant a test or a sandbox
    silently wrote into the live facts file.
    """
    # CAPRI_ROOT lets a test point the whole instance at a scratch directory
    # with one line. Without it, every ad-hoc script that constructs Capri()
    # writes into the real facts file and the real episodic memory - which is
    # exactly what happened: 62 test probes ended up in Neo's memory, and
    # recall then fed his assistant its own test answers back as if they were
    # real conversation.
    import os
    env_root = os.environ.get("CAPRI_ROOT")
    if path is None and env_root:
        p = (Path(env_root) / "config.yaml").resolve()
    else:
        p = Path(path).resolve() if path else ROOT / "config.yaml"
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg["_root"] = p.parent
    cfg["_config_path"] = p
    return cfg
