"""TickTick wiring, with no network and no token.

The client takes an injected opener, so these run anywhere and cannot
accidentally hit Neo's real account.
"""
from __future__ import annotations
import pathlib, sys, tempfile, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from capri.integrations.ticktick import TickTick, TickTickError
from capri.tools.registry import Registry, Tier
from capri.tools.tasks import build

FAKE = {
    "/open/v1/project": [{"id": "p1", "name": "Uni"}, {"id": "p2", "name": "Life"}],
    "/open/v1/project/p1/data": {"tasks": [
        {"id": "t1", "projectId": "p1", "title": "CS101 assignment submission",
         "dueDate": "2026-11-06T17:00:00+0000", "priority": 5, "status": 0},
        {"id": "t2", "projectId": "p1", "title": "Read lecture notes",
         "priority": 1, "status": 0},
        {"id": "t5", "projectId": "p1", "title": "Old finished thing",
         "priority": 0, "status": 2},
    ]},
    "/open/v1/project/p2/data": {"tasks": [
        {"id": "t3", "projectId": "p2", "title": "Buy groceries",
         "priority": 0, "status": 0},
        {"id": "t4", "projectId": "p2", "title": "New Genshin banner",
         "priority": 0, "status": 0},
    ]},
}

def opener(method, path, body=None):
    if path not in FAKE:
        raise TickTickError(f"unexpected call: {method} {path}")
    return FAKE[path]

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    ok, fail = ok + bool(cond), fail + (not cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if detail and not cond: print(f"          {detail}")

tmp = pathlib.Path(tempfile.mkdtemp())

# --- not connected: tools must say so, not crash ---
tt = TickTick(tmp / "missing.json", opener=opener)
reg = Registry(max_tier=Tier.READ_ONLY)
for t in build(tt): reg.register(t)
r = reg.call("list_tasks", {})
check("unconnected is reported, not raised", not r.ok and "not connected" in r.error)

# --- connected ---
tok = tmp / "tok.json"; tok.write_text(json.dumps({"access_token": "x"}))
tt2 = TickTick(tok, opener=opener)
reg2 = Registry(max_tier=Tier.READ_ONLY)
for t in build(tt2): reg2.register(t)

body = reg2.call("list_tasks", {}).content
check("completed tasks are excluded", "Old finished thing" not in body, body)
check("assignment is TIER 0", "TIER 0" in body and
      body.index("CS101") > body.index("TIER 0"), body)
check("genshin is TIER 3", "TIER 3" in body, body)
check("tiers are in order", body.index("TIER 0") < body.index("TIER 3"), body)

urgent = reg2.call("urgent_tasks", {}).content
check("urgent includes the assignment", "CS101" in urgent, urgent)
check("urgent excludes groceries", "groceries" not in urgent, urgent)
check("urgent excludes genshin", "Genshin" not in urgent, urgent)

# --- the registry still refuses anything above the ceiling ---
from capri.tools.registry import Tool, Result
reg2.register(Tool("delete_everything", "nope", {"properties": {}},
                   Tier.DANGEROUS, lambda: Result(True, "boom")))
r = reg2.call("delete_everything", {})
check("tier 2 blocked by the ceiling", not r.ok and "blocked" in r.error, r.error)
check("blocked tool is hidden from the model",
      "delete_everything" not in reg2.describe(), reg2.describe())
check("the attempt is still audited",
      any(a["tool"] == "delete_everything" for a in reg2.audit))

print(f"\n  {ok}/{ok+fail} passed")
sys.exit(1 if fail else 0)
