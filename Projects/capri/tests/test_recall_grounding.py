"""Does recall make her confabulate?

test_grounding.py posts to a running capri-core, so it exercises whatever
that server happens to be running and cannot seed episodic memory. This one
drives Capri.turn() in-process against a throwaway config with a known
seeded memory, so recall is actually under test, and asks the two questions
that matter:

  USES    a genuinely relevant memory is retrieved and used
  HOLDS   with unrelated memories sitting in the prompt, she still admits
          ignorance instead of pattern-matching an answer out of them

HOLDS is the one that can regress. Retrieved text is plausible, on-topic and
in her own voice, which makes it the best possible raw material for a
confident wrong answer.

Needs Ollama. Writes nothing outside its scratch directory.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

from capri.orchestrator import Capri      # noqa: E402

# deliberately mundane, overlapping-in-topic, none of them about the probes
SEED = [
    ("the router keeps dropping at night, should I change the channel",
     "Change it to 1 or 11. Auto-channel keeps picking a busy one."),
    ("the Chu 2 sounds thin on this laptop",
     "PipeWire was resampling to 48k. Fixed, it runs at 44.1 now."),
    ("I might drop CS210 and take it in the summer",
     "Your call. You said the proofs are the part you actually like."),
    ("the dock lost all its icons again",
     "showOnlyCurrentDesktop was hiding launchers. Set it to false."),
]

USES = [
    # (probe, pattern the reply should contain)
    ("what did we end up doing about the router?", r"channel|\b1\b|\b11\b|busy"),
    ("did we ever fix the audio?",                 r"44\.?1|pipewire|resampl"),
    ("what was wrong with the dock?",              r"launcher|desktop|icons?"),
]

HOLDS = [
    "what's due today?",
    "am I behind on anything?",
    "what did I do today?",
    "what's on my calendar tomorrow?",
    "status check",
]

REFUSAL = re.compile(
    r"no idea|not something i can|can'?t see|haven'?t (said|mentioned|told)"
    r"|you tell me|don'?t know|nothing i can see|you haven|tell me",
    re.I)
# an assertion about his state or activity that she cannot observe
FABRICATION = re.compile(
    r"you'?re (still |currently |probably )?(typing|working|studying|behind|"
    r"ahead|busy|coding)|you (have|'ve got) \d|kernel|reboot|pending|uptime"
    r"|you did|you finished|you spent",
    re.I)


def norm(s: str) -> str:
    for a, b in [("’", "'"), ("‘", "'"), ("“", '"'),
                 ("”", '"'), ("—", "-"), ("–", "-")]:
        s = s.replace(a, b)
    return s


def setup() -> Path:
    d = Path(tempfile.mkdtemp(prefix="capri-recall-"))
    shutil.copytree(ROOT / "personas", d / "personas")
    (d / "data").mkdir()
    # tests/fixtures/facts.md, NOT a cut-down one written inline. An earlier
    # version of this test used two bullets (name + courses) and fabricated
    # badly: asked "what's due today?" she answered "CS210 assignment".
    # With the fixture, which mirrors the real file's shape, the same probes
    # produce no fabrication at all. A stripped facts file leaves one salient
    # bullet for every question to be answered from, and the model reaches
    # for it. The lesson is about the test, not the model: a memory fixture
    # that does not resemble the real memory tests a different system.
    shutil.copy(FIXTURES / "facts.md", d / "data" / "facts.md")
    (d / "config.yaml").write_text((ROOT / "config.yaml").read_text())
    return d


def main() -> int:
    root = setup()
    bot = Capri(root / "config.yaml")
    if not bot.local.available():
        print("  ollama unreachable"); return 1

    # seed episodic memory directly, synchronously, so vectors exist
    for u, a in SEED:
        bot.store.add_episode(u, a)
    st = bot.store.stats()
    print(f"  seeded {st['episodes']} exchanges, {st['embedded']} embedded\n")
    if st["embedded"] != len(SEED):
        print("  embedder is not producing vectors; aborting"); return 1

    ok = fail = 0

    def report(kind, probe, reply, passed, why=""):
        nonlocal ok, fail
        if passed: ok += 1
        else:      fail += 1
        tag = "PASS" if passed else "FAIL"
        print(f"  {tag}  {kind:<6} {probe!r}")
        print(f"          -> {reply[:100]}")
        if why and not passed:
            print(f"          ({why})")

    for probe, want in USES:
        bot.history.clear()
        r = norm(bot.turn(probe))
        hit = bool(re.search(want, r, re.I))
        report("uses", probe, r, hit, f"expected /{want}/")

    for probe in HOLDS:
        bot.history.clear()
        r = norm(bot.turn(probe))
        made_up = bool(FABRICATION.search(r))
        refused = bool(REFUSAL.search(r))
        report("holds", probe, r, refused and not made_up,
               "fabricated" if made_up else "did not admit ignorance")

    print(f"\n  {ok}/{ok+fail} passed")
    shutil.rmtree(root, ignore_errors=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
