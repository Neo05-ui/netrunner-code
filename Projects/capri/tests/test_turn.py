"""Exercise turn() itself, with a fake brain.

Twice in one evening an edit put a line that USED a variable above the line
that SET it, and every single turn raised UnboundLocalError. The other suites
missed it because none of them call turn() - they test the Guard, the store
and the registry in isolation. A fast test that actually walks the turn loop
is what catches that class of mistake, so here it is.

No Ollama: the provider is replaced with a stub that records what it was
given, which also lets us assert WHICH instructions reached the model.
"""
from __future__ import annotations
import os, pathlib, shutil, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

d = pathlib.Path(tempfile.mkdtemp(prefix="turn-"))
shutil.copytree(ROOT / "personas", d / "personas")
(d / "data").mkdir()
(d / "data" / "facts.md").write_text("# Facts\n\n- His name is Neo.\n")
shutil.copy(ROOT / "config.yaml", d / "config.yaml")
os.environ["CAPRI_ROOT"] = str(d)

from capri.orchestrator import Capri            # noqa: E402
from capri.providers.base import Reply          # noqa: E402


class Stub:
    model = "stub"
    def __init__(self): self.seen = []
    def available(self): return True
    def chat(self, messages, tools=None):
        self.seen.append({"messages": messages, "tools": tools})
        return Reply(text="ok", model="stub", latency_ms=1)


ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    ok, fail = ok + bool(cond), fail + (not cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if detail and not cond: print(f"          {detail}")

bot = Capri()
stub = Stub(); bot.local = stub

def last(text):
    stub.seen.clear(); bot.history.clear()
    out = bot.turn(text)
    return out, stub.seen[-1]

# the bug that bit twice: any turn at all must simply not raise
r, call = last("yo whats up")
check("a plain turn completes", r == "ok")
check("no tools offered for a greeting", call["tools"] is None)

sys_msgs = " ".join(m["content"] for m in call["messages"] if m["role"] == "system")
check("told not to invent machine state", "taken no readings" in sys_msgs, sys_msgs[-200:])

# a tool question gets tools, and no 'you took no readings' instruction
r, call = last("what's my battery at?")
check("tools offered for a hardware question", call["tools"] is not None)
sys_msgs = " ".join(m["content"] for m in call["messages"] if m["role"] == "system")
check("no false 'no readings' claim when tools are offered",
      "taken no readings" not in sys_msgs)

# a disclosure gets the engage instruction and NO tools
r, call = last("i've had a terrible week")
sys_msgs = " ".join(m["content"] for m in call["messages"] if m["role"] == "system")
check("disclosure gets no tools", call["tools"] is None)
check("disclosure gets the engage instruction", "NOT a request for information" in sys_msgs)

# the clock must be at the tail, never inside the cached system prompt
r, call = last("hello")
first_sys = call["messages"][0]["content"]
check("clock is NOT in the cached prefix", "Right now it is" not in first_sys)
check("clock IS present at the tail",
      any("Right now it is" in m["content"] for m in call["messages"][1:]))

# memory commands never reach the model at all
stub.seen.clear(); bot.history.clear()
out = bot.turn("remember that the bike code is 4417")
check("remember bypasses the model", not stub.seen)
check("remember is confirmed to the user", "4417" in out, out)
out = bot.turn("forget the bike code")
check("forget bypasses the model", not stub.seen)

# a dead brain must not crash the turn
class Dead(Stub):
    def chat(self, messages, tools=None):
        return Reply(text="", model="stub", error="boom")
bot.local = Dead()
bot.history.clear()
out = bot.turn("hello")
# assert the property, not the exact sentence: a failure must never surface
# as a stack trace or name the plumbing, and must still invite him to carry
# on. (This used to match the literal word "brain" and broke the moment the
# message was improved - a test tied to wording, not behaviour.)
leaky = any(w in out.lower() for w in
            ("ollama", "traceback", "exception", "error", "http", "127.0.0.1"))
check("a failed provider says something human", bool(out.strip()) and not leaky, out)

print(f"\n  {ok}/{ok+fail} passed")
shutil.rmtree(d, ignore_errors=True)
sys.exit(1 if fail else 0)
