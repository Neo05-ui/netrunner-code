"""Phase 1 tests. None of these need Ollama running."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capri.config import load
from capri.memory import Facts
from capri.persona import Persona
from capri.providers.base import Reply

ROOT = Path(__file__).resolve().parent.parent


def test_config_loads():
    cfg = load()
    assert cfg["brain"]["local"]["model"]
    assert cfg["persona"] == "capri"
    assert cfg["brain"]["cloud"]["enabled"] is False, "cloud must stay off until the Guard exists"


def test_persona_fills_placeholders():
    p = Persona(ROOT, "capri")
    out = p.system_prompt(facts="- likes terse answers", user_name="Neo")
    assert "{{facts}}" not in out
    assert "{{user_name}}" not in out
    assert "{{now}}" not in out
    assert "likes terse answers" in out
    assert "Neo" in out


def test_persona_hot_reload(tmp_path=None):
    import shutil
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "personas", tmp / "personas")
    p = Persona(tmp, "capri")
    first = p.system_prompt(facts="x", user_name="Neo")
    md = tmp / "personas" / "capri" / "persona.md"
    md.write_text(md.read_text() + "\nYou now speak only in haiku.\n")
    import os, time
    os.utime(md, (time.time() + 1, time.time() + 1))
    second = p.system_prompt(facts="x", user_name="Neo")
    assert "haiku" in second and "haiku" not in first


def test_facts_roundtrip():
    tmp = Path(tempfile.mkdtemp()) / "facts.md"
    f = Facts(tmp)
    f.add("Prefers crimson and acid green")
    assert "crimson" in f.read()
    before = f.read()
    f.add("Prefers crimson and acid green")   # duplicate
    assert f.read() == before, "duplicate facts must not be appended twice"


def test_reply_ok_flag():
    assert Reply(text="hi", model="m").ok
    assert not Reply(text="", model="m", error="boom").ok


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n  {len(fns)-failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
