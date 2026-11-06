"""Tier 0 TickTick tools, plus the briefing that turns tasks into tiers.

The briefing is the point. A flat list of twenty tasks is noise; Neo's matrix
exists so that CRITICAL OVERLOAD is visibly separate from DOPAMINE DROP, and
so Capri knows which ones she is allowed to interrupt him about.
"""
from __future__ import annotations

from ..priority import TIER_NAMES, classify
from .registry import Result, Tier, Tool


def build(client) -> list[Tool]:
    def _tiered():
        tasks = client.all_open()
        try:
            names = client.project_names()
        except Exception:                       # noqa: BLE001
            names = {}
        rows = []
        for t in tasks:
            tier, why = classify(t.title, priority=t.priority, due=t.due,
                                 project=names.get(t.project_id, ""))
            rows.append((tier, t, why))
        return sorted(rows, key=lambda r: (r[0], r[1].due or "9999"))

    def list_tasks() -> Result:
        if not client.connected():
            return Result(False, error="TickTick is not connected yet")
        rows = _tiered()
        if not rows:
            return Result(True, content="No open tasks.")
        out, current = [], None
        for tier, t, _ in rows:
            if tier != current:
                current = tier
                out.append(f"\nTIER {tier} — {TIER_NAMES[tier]}")
            due = f"  (due {t.due[:16].replace('T', ' ')})" if t.due else ""
            out.append(f"  - {t.title}{due}")
        return Result(True, content="\n".join(out).strip())

    def urgent_tasks() -> Result:
        """Tier 0 and 1 only — the ones she may actually interrupt about."""
        if not client.connected():
            return Result(False, error="TickTick is not connected yet")
        rows = [r for r in _tiered() if r[0] <= 1]
        if not rows:
            return Result(True, content="Nothing urgent.")
        return Result(True, content="\n".join(
            f"  T{tier} {t.title}" + (f"  (due {t.due[:16].replace('T',' ')})"
                                      if t.due else "")
            for tier, t, _ in rows))

    return [
        Tool("list_tasks",
             "Neo's open TickTick tasks, grouped by interrupt tier.",
             {"properties": {}}, Tier.READ_ONLY, list_tasks, timeout_s=20),
        Tool("urgent_tasks",
             "Only the tier 0 and tier 1 tasks — deadlines and directives.",
             {"properties": {}}, Tier.READ_ONLY, urgent_tasks, timeout_s=20),
    ]
