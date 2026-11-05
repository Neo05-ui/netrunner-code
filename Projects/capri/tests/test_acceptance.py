"""The blueprint's Phase 2 acceptance test, run literally.

  "Tell her a new fact, restart the whole app, and ask about it.
   Delete it with 'forget' and confirm she no longer knows it."

Each step runs in its OWN python process against a throwaway config, so
"restart" means what it says: no shared objects, no warm state, nothing but
what reached the disk. Needs Ollama up.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET = "his bike is locked with the code 4417"
PROBE = "what code is my bike locked with?"


def setup() -> Path:
    """A scratch Capri: real persona and model, empty memory."""
    d = Path(tempfile.mkdtemp(prefix="capri-accept-"))
    shutil.copytree(ROOT / "personas", d / "personas")
    (d / "data").mkdir()
    (d / "data" / "facts.md").write_text("# Facts about Neo\n\n- His name is Neo.\n")
    cfg = (ROOT / "config.yaml").read_text()
    (d / "config.yaml").write_text(cfg)
    return d


def run(root: Path, text: str) -> str:
    """One fresh process, one turn, then the process dies."""
    code = (
        "import sys,json;sys.path.insert(0,%r);"
        "from capri.orchestrator import Capri;"
        "print(json.dumps(Capri(%r).turn(%r)))"
        % (str(ROOT), str(root / "config.yaml"), text)
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("turn failed:\n" + r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> int:
    root = setup()
    print(f"  scratch root: {root}\n")
    ok = fail = 0

    def check(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  PASS  {name}")
        else:
            fail += 1
            print(f"  FAIL  {name}")
        if detail:
            print(f"          {detail}")

    # 1. tell her a new fact
    r = run(root, f"remember that {SECRET}")
    check("1. accepts the fact", "4417" in r, f"-> {r}")

    # it must be on disk before the process that learned it is gone
    facts = (root / "data" / "facts.md").read_text()
    check("2. fact is written to facts.md", "4417" in facts,
          "-> " + facts.strip().splitlines()[-1])

    # 3. RESTART, then ask. New process, cold history.
    r = run(root, PROBE)
    check("3. knows it after a full restart", "4417" in r, f"-> {r}")

    # 4. forget it
    r = run(root, "forget the bike code")
    check("4. confirms the deletion", "4417" in r or "bike" in r.lower(), f"-> {r}")
    facts = (root / "data" / "facts.md").read_text()
    check("5. fact is gone from facts.md", "4417" not in facts)

    # 6. RESTART again, ask again. She must not know, and must not invent.
    r = run(root, PROBE)
    knows = "4417" in r
    invented = bool(re.search(r"\b\d{3,5}\b", r))
    check("6. no longer knows it", not knows, f"-> {r}")
    check("7. does not invent a replacement code", not invented)

    print(f"\n  {ok}/{ok+fail} passed")
    shutil.rmtree(root, ignore_errors=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
