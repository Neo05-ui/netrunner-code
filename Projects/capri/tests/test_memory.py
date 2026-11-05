"""Phase 2 unit tests: no Ollama needed (embeddings degrade to None)."""
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from capri.memory import Facts
from capri.store import Store
from capri import commands

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else:    fail += 1; print(f"  FAIL  {name}")

tmp = pathlib.Path(tempfile.mkdtemp())

# --- facts survive a new object (i.e. a restart) -------------------------
fp = tmp / "facts.md"
f1 = Facts(fp, who="Neo")
f1.add("my router password is in the blue notebook")
del f1
f2 = Facts(fp, who="Neo")
check("fact survives a fresh Facts object", "blue notebook" in f2.read())

# --- forget really removes it -------------------------------------------
gone = f2.remove("router password")
check("forget returns the bullet", gone is not None and "blue notebook" in gone)
f3 = Facts(fp, who="Neo")
check("fact is gone after reload", "blue notebook" not in f3.read())

# --- forget refuses a weak match ----------------------------------------
before = f3.read()
check("forget ignores unrelated text", f3.remove("helicopter rental") is None)
check("file unchanged on failed forget", f3.read() == before)

# --- command parsing -----------------------------------------------------
check("parses remember", commands.parse("remember that X is Y") == ("remember", "X is Y"))
check("parses forget", commands.parse("forget X") == ("forget", "X"))
check("parses list", commands.parse("what do you know about me")[0] == "list")
check("ignores a plain question", commands.parse("what's my name?") is None)
check("ignores 'do you remember ...'", commands.parse("do you remember the router") is None)

# --- store writes turns, and degrades without an embedder ---------------
st = Store(tmp / "t.db", embed_host="http://127.0.0.1:1")   # dead port
st.add_turn("user", "hello")
st.add_turn("assistant", "hi")
check("turns are persisted", st.stats()["turns"] == 2)
st.add_episode("q", "a")
check("episode stored even with no embedder", st.stats()["episodes"] == 1)
check("no vector when embedder is down", st.stats()["embedded"] == 0)
check("recall returns nothing rather than crashing", st.recall("anything") == [])

st2 = Store(tmp / "t.db", embed_host="http://127.0.0.1:1")
check("turns survive reopening the db", st2.stats()["turns"] == 2)

# --- unindex: forgetting must stop recall handing it back ---------------
import sqlite3
st3 = Store(tmp / "u.db", embed_host="http://127.0.0.1:1")
with sqlite3.connect(st3.path) as c:
    # two episodes WITH vectors, as if they had been embedded for real
    c.execute("INSERT INTO episodes (ts,session,summary,vec) VALUES (?,?,?,?)",
              ("t", "s", "Neo: what's due\nCapri: CS101 assignment at 5pm", b"\x00" * 4))
    c.execute("INSERT INTO episodes (ts,session,summary,vec) VALUES (?,?,?,?)",
              ("t", "s", "Neo: router drops\nCapri: change the channel", b"\x00" * 4))
check("two episodes are indexed", st3.stats()["embedded"] == 2)
n = st3.unindex("CS101")
check("unindex reports one hit", n == 1)
check("one episode left indexed", st3.stats()["embedded"] == 1)
check("the record itself is kept", st3.stats()["episodes"] == 2)
check("unindex of nothing is 0", st3.unindex("helicopter") == 0)

# forget wires facts + unindex together
f4 = Facts(tmp / "f2.md", who="Neo")
f4.add("the bike code is 4417")
msg = commands.handle("forget", "bike code", f4, st3)
check("forget reports the fact", "4417" in msg)
check("forget leaves no matching fact", "4417" not in f4.read())

print(f"\n  {ok}/{ok+fail} passed")
sys.exit(1 if fail else 0)
